"""Maintain public CMS endpoints; never request episode/media URLs or run remote code."""
import argparse
import concurrent.futures
import gzip
import html
import io
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LIMIT = 2 * 1024 * 1024


def read_bytes(url, headers=None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid public HTTP endpoint')
    request = urllib.request.Request(url, headers={'User-Agent': 'CatalogCheck/1.0', 'Accept-Encoding': 'identity', **(headers or {})})
    with urllib.request.urlopen(request, timeout=14) as response:
        data = response.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError('Response exceeds 2 MiB')
    if data.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
            data = compressed.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError('Decoded response exceeds 2 MiB')
    return data


def read(url):
    return read_bytes(url).decode('utf-8-sig', errors='replace')


def discover(body):
    found = re.findall(r'https?://[^\s<>"\x27`]+?\.php/provide/vod[^\s<>"\x27`]*', html.unescape(body), re.I)
    result = []
    for value in found:
        value = value.split('?', 1)[0].rstrip('.,;)]}')
        value = re.sub(r'/at/(?:xmlsea|xml|json)/?$', '/', value, flags=re.I).rstrip('/') + '/'
        value = value.replace('/provide//', '/provide/')
        if any(part in value.lower() for part in ('yun/', 'feifan/')):
            continue
        if value not in result:
            result.append(value)
    return sorted(result, key=lambda x: ('from/' not in x, not x.startswith('https:')))[:4]


def has_hls(items):
    for item in items:
        for line in str(item.get('vod_play_url', '')).split('$$$'):
            for episode in line.split('#'):
                url = episode.rsplit('$', 1)[-1]
                parsed = urllib.parse.urlsplit(url)
                if parsed.scheme in ('http', 'https') and parsed.netloc and parsed.path.lower().endswith('.m3u8'):
                    return True
    return False


def inspect(api):
    def get(**params):
        time.sleep(1)
        payload = json.loads(read(api + ('&' if '?' in api else '?') + urllib.parse.urlencode(params)))
        if not isinstance(payload, dict):
            raise ValueError('CMS response must be an object')
        return payload
    categories = get(ac='list').get('class')
    if not isinstance(categories, list) or not any(isinstance(c, dict) and c.get('type_id') is not None for c in categories):
        raise ValueError('Missing CMS categories')
    page = get(ac='detail', pg=1).get('list')
    if not isinstance(page, list):
        raise ValueError('Missing CMS items')
    sample = next((v for v in page if isinstance(v, dict) and v.get('vod_id') is not None and v.get('vod_name')), None)
    if sample is None:
        raise ValueError('No usable CMS item')
    details = get(ac='detail', ids=sample['vod_id']).get('list', [])
    matched = [v for v in details if isinstance(v, dict) and str(v.get('vod_id')) == str(sample['vod_id'])]
    if not has_hls(matched):
        raise ValueError('No matching direct HLS episode metadata')
    search_error = ''
    try:
        search = get(ac='detail', wd=sample['vod_name'], pg=1).get('list', [])
        searchable = any(isinstance(v, dict) and str(v.get('vod_id')) == str(sample['vod_id']) for v in search)
    except Exception as error:
        searchable = False
        search_error = type(error).__name__
    return {'categories': len(categories), 'items': len(page), 'search': searchable, 'search_error': search_error}


def check(entry, previous):
    result = {'key': entry['key'], 'name': entry['name'], 'homepage': entry['homepage'], 'ok': False, 'attempts': []}
    candidates = list(entry['candidates'])
    if previous and previous.get('api') not in candidates:
        candidates.insert(0, previous['api'])
    # Only discover from this explicitly reviewed official help page, and only on recovery.
    if not candidates:
        try:
            candidates = discover(read(entry['help']))
        except Exception as error:
            result['discovery_error'] = type(error).__name__
    tested = set()
    for recovery in (False, True):
        for api in candidates[:4]:
            if api in tested:
                continue
            tested.add(api)
            try:
                evidence = inspect(api)
                site = {'key': entry['key'], 'name': entry['name'], 'type': 1, 'api': api,
                        'searchable': int(evidence['search']), 'quickSearch': int(evidence['search']), 'filterable': 0}
                result.update(evidence, ok=True, site=site)
                return result
            except Exception as error:
                # Keep diagnostic messages bounded; no bodies, media links or tokens are stored.
                result['attempts'].append({'api': api, 'error': type(error).__name__ + ': ' + str(error)[:120]})
        if recovery:
            break
        try:
            candidates = discover(read(entry['help']))
        except Exception as error:
            result['discovery_error'] = type(error).__name__
    result['note'] = entry.get('note', 'No endpoint passed metadata validation')
    return result


def reconcile(results, previous, old_state):
    old = {site['key']: site for site in previous}
    sites, state = [], {}
    for result in results:
        key = result['key']
        prior = old_state.get(key, {})
        if result['ok']:
            site = result['site']
            sites.append(site)
            state[key] = {'failures': 0, 'last_good': site}
        else:
            failures = prior.get('failures', 0) + 1
            last = old.get(key) or prior.get('last_good')
            state[key] = {'failures': failures}
            if last:
                state[key]['last_good'] = last
                if failures < 3:
                    sites.append(last)
    if not sites and previous:
        sites = list(previous)
        for site in previous:
            state.setdefault(site['key'], {})['retained_outage'] = True
    return sites, state



def apply_selection(sites, previous, selection):
    if selection is None:
        return sites, False
    keys = selection.get('preferred_keys')
    if not isinstance(keys, list) or not keys or any(not isinstance(k, str) for k in keys) or len(set(keys)) != len(keys):
        raise ValueError('Quality selection must contain unique reviewed source keys')
    current = {site['key']: site for site in sites}
    selected = [current[key] for key in keys if key in current]
    if selected:
        return selected, False
    old = {site['key']: site for site in previous}
    retained = [old[key] for key in keys if key in old]
    if not retained:
        raise ValueError('No reviewed source remains; refusing an unreviewed replacement')
    return retained, True


def load(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalog', type=Path, default=Path('catalog.json'))
    parser.add_argument('--output', type=Path, default=Path('published'))
    parser.add_argument('--inspect-only', action='store_true')
    args = parser.parse_args()
    catalog = load(args.catalog, [])
    if not catalog or len({e['key'] for e in catalog}) != len(catalog):
        raise ValueError('Empty or duplicate source catalog')
    args.output.mkdir(parents=True, exist_ok=True)
    previous = load(args.output / 'vod.json', {'sites': []})['sites']
    health = load(args.output / 'health.json', {'state': {}})
    by_key = {site['key']: site for site in previous}
    for key, state in health['state'].items():
        if key not in by_key and state.get('last_good'):
            by_key[key] = state['last_good']
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda entry: check(entry, by_key.get(entry['key'])), catalog))
    sites, state = reconcile(results, previous, health['state'])
    selection = load(args.output / 'selection.json', None)
    sites, retained_preferred = apply_selection(sites, previous, selection)
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'scope': 'metadata-only; no media requested',
              'total': len(catalog), 'healthy': sum(r['ok'] for r in results), 'published': len(sites), 'results': results, 'state': state,
              'quality_review_applied': selection is not None, 'quality_checked_at': selection.get('checked_at') if selection else None,
              'retained_preferred_snapshot': retained_preferred}
    write(args.output / 'health.json', report)
    if not sites:
        raise RuntimeError('No valid source; refusing to publish an empty configuration')
    if not args.inspect_only:
        write(args.output / 'vod.json', {'sites': sites, 'parses': [], 'lives': []})
    print(json.dumps({'total': len(catalog), 'healthy': report['healthy'], 'published': len(sites), 'media_requests': 0}))


if __name__ == '__main__':
    main()
