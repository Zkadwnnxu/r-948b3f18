"""Bounded source quality observations. Decode only to null, never to devices or files."""
import argparse
import concurrent.futures
import json
import os
import queue
import re
import shutil
import statistics
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
import update

UA = 'Mozilla/5.0 (Linux; Android 12; TV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
POLICY = {'baseline_samples': 2, 'baseline_seconds': 60, 'confirmation_seconds': 120,
          'max_progress_gap_seconds': 3, 'max_active_elapsed_ratio': 1.15,
          'max_median_first_frame_seconds': 8, 'max_single_first_frame_seconds': 12,
          'cover_required': True, 'decode_errors_allowed': 0}
SCOPE = 'Cloud Linux FFmpeg software decode to null; no display/audio devices. Sample observations for this runner/network, not TV hardware or long-term availability.'


def redact(value):
    return re.sub(r'https?://[^\s\x27\x22]+', '<url>', str(value))[:400]


def web(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or any(ord(c) < 32 for c in url):
        raise ValueError('Invalid public media address')
    return url


def command(binary, url, seconds, ca_file=None):
    web(url)
    args = [binary, '-nostdin', '-hide_banner', '-loglevel', 'info', '-nostats', '-stats_period', '0.25',
            '-progress', 'pipe:1', '-filter_threads', '1', '-threads', '2', '-re', '-rw_timeout', '12000000',
            '-user_agent', UA, '-protocol_whitelist', 'http,https,tcp,tls,crypto']
    if url.startswith('https://'):
        args += ['-tls_verify', '1']
    if ca_file:
        args += ['-ca_file', str(ca_file)]
    return args + ['-i', url, '-map', '0:v:0', '-map', '0:a:0?', '-threads', '2', '-t', str(seconds), '-f', 'null', '-']


def decode(binary, url, seconds, ca_file=None):
    start = time.monotonic()
    process = subprocess.Popen(command(binary, url, seconds, ca_file), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', errors='replace', bufsize=1,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    events, logs = queue.Queue(), []
    def output():
        for line in process.stdout:
            events.put((time.monotonic(), line.strip()))
    def logging():
        for line in process.stderr:
            if len(logs) < 2000:
                logs.append(redact(line.strip()))
    threads = [threading.Thread(target=output, daemon=True), threading.Thread(target=logging, daemon=True)]
    for thread in threads:
        thread.start()
    state = {}; first = last_at = completion = None
    frames = 0; gap = duration = 0; stopped = ''
    try:
        while process.poll() is None or not events.empty():
            now = time.monotonic()
            if process.poll() is None:
                if first is None and now - start > 30:
                    stopped = 'first_frame_timeout'; process.kill()
                elif last_at and now - last_at > 18:
                    stopped = 'decode_stalled'; process.kill()
                elif now - start > seconds + 55:
                    stopped = 'wall_timeout'; process.kill()
            try:
                at, line = events.get(timeout=.2)
            except queue.Empty:
                continue
            if '=' not in line:
                continue
            key, value = line.split('=', 1); state[key] = value.strip()
            if key == 'progress':
                count = int(state.get('frame', '0') or '0')
                current = int(state.get('out_time_us', '0') or '0') / 1e6
                duration = max(duration, current)
                if count > frames:
                    if first is None:
                        first = at - start
                    if last_at is not None:
                        gap = max(gap, at - last_at)
                    last_at, frames = at, count
                if completion is None and current >= seconds - .5:
                    completion = at - start
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=2)
        process.stdout.close(); process.stderr.close()
    errors = [line for line in logs if re.search(r'error|corrupt|failed|invalid data|timed out|certificate|forbidden|not found', line, re.I)]
    return {'returncode': process.returncode, 'first_frame_seconds': round(first, 3) if first is not None else None,
            'decoded_seconds': round(duration, 3), 'frames': frames, 'audio_stream': any(re.search(r'Stream #0:[0-9].*Audio:', line) for line in logs),
            'max_progress_gap_seconds': round(gap, 3), 'completion_wall_seconds': completion,
            'wall_seconds': round(time.monotonic() - start, 3), 'termination': stopped, 'errors': errors[-12:]}


def cover(binary, url):
    try:
        start = time.monotonic()
        data = update.read_bytes(web(url), {'User-Agent': UA})
        image = data.startswith((b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n', b'GIF8')) or data.startswith(b'RIFF') and data[8:12] == b'WEBP'
        if not image:
            raise ValueError('Cover is not a supported image')
        result = subprocess.run([binary, '-nostdin', '-hide_banner', '-loglevel', 'error', '-protocol_whitelist', 'pipe',
                                 '-i', 'pipe:0', '-frames:v', '1', '-f', 'null', '-'], input=data, capture_output=True, timeout=15)
        if result.returncode:
            raise ValueError('Cover image decode failed')
        return {'ok': True, 'seconds': round(time.monotonic() - start, 3)}
    except Exception as error:
        return {'ok': False, 'error': redact(type(error).__name__ + ': ' + str(error))}


def grade(sample, target):
    d, reasons = sample.get('decode', {}), []
    if not sample.get('cover', {}).get('ok'): reasons.append('cover_failed')
    if d.get('returncode') != 0: reasons.append('decode_failed')
    if d.get('decoded_seconds', 0) < target - .5: reasons.append('duration_incomplete')
    first = d.get('first_frame_seconds')
    if first is None or first > 12: reasons.append('slow_or_missing_first_frame')
    if not d.get('audio_stream'): reasons.append('missing_audio_decode')
    if d.get('frames', 0) < target * 5: reasons.append('insufficient_video_frames')
    if d.get('max_progress_gap_seconds', 0) > 3: reasons.append('progress_gap')
    if d.get('errors'): reasons.append('stream_errors')
    completion = d.get('completion_wall_seconds')
    ratio = (completion - first) / (target - .5) if completion is not None and first is not None else None
    if ratio is None or ratio > 1.15: reasons.append('slow_continuous_progress')
    return {**sample, 'target_seconds': target, 'active_elapsed_ratio': round(ratio, 3) if ratio is not None else None,
            'passed': not reasons, 'reasons': reasons}


def qualifies(report):
    samples = report.get('samples', [])
    starts = [s.get('decode', {}).get('first_frame_seconds') for s in samples]
    return len(samples) >= 3 and all(s.get('passed') for s in samples) and all(v is not None for v in starts) \
        and sum(s.get('target_seconds') == 60 for s in samples) >= 2 \
        and any(s.get('target_seconds', 0) >= 120 for s in samples) and statistics.median(starts) <= 8


def choose(reports, previous, old_state):
    passed = [r for r in reports if qualifies(r)]
    passed.sort(key=lambda r: statistics.median(s['decode']['first_frame_seconds'] for s in r['samples']))
    sites = [r['site'] for r in passed]
    good = {s['key'] for s in sites}; state = {}; retained = []
    for report in reports:
        key = report['key']
        state[key] = {'failures': 0 if key in good else old_state.get(key, {}).get('failures', 0) + 1}
    for site in previous:
        key = site['key']
        if key not in state: state[key] = {'failures': old_state.get(key, {}).get('failures', 0) + 1}
        if key not in good and state[key]['failures'] < 3:
            sites.append(site); retained.append(key)
    snapshot = not passed
    if not sites and previous:
        sites = list(previous); retained = [s['key'] for s in sites]
    return {'sites': sites, 'keys': [s['key'] for s in sites], 'state': state,
            'retained_keys': retained, 'retained_snapshot': snapshot}


def due(report, now=None):
    return not report or (time.time() if now is None else now) - report.get('attempted_epoch', 0) >= 24 * 3600


def cms(site, **params):
    time.sleep(1)
    body = update.read_bytes(site['api'] + ('&' if '?' in site['api'] else '?') + urllib.parse.urlencode(params), {'User-Agent': UA})
    payload = json.loads(body)
    if not isinstance(payload, dict): raise ValueError('Invalid CMS object')
    return payload


def episode(item):
    for line in str(item.get('vod_play_url', '')).split('$$$'):
        for row in line.split('#'):
            url = row.rsplit('$', 1)[-1]
            p = urllib.parse.urlsplit(url)
            if p.scheme in ('http', 'https') and p.path.lower().endswith('.m3u8'):
                return web(url)
    return ''


def samples(site):
    found, ids = [], set()
    for query, names in [('流浪地球', {'流浪地球', '流浪地球2'}), ('狂飙', {'狂飙'})]:
        try:
            rows = cms(site, ac='detail', wd=query, pg=1).get('list', [])
            match = next((v for v in rows if str(v.get('vod_name', '')).strip() in names and v.get('vod_id') not in ids), None)
            if match:
                found.append(match); ids.add(match['vod_id'])
        except Exception:
            # Search can be disabled while category and detail endpoints remain available.
            continue
    if len(found) < 2:
        for item in cms(site, ac='detail', pg=1).get('list', []):
            if len(found) >= 2: break
            if item.get('vod_id') in ids or any(k in str(item.get('type_name', '')) + str(item.get('vod_name', '')) for k in ['解说', '伦理', '写真', '成人', '预告']): continue
            if episode(item): found.append(item); ids.add(item['vod_id'])
    return found[:2]



def preflight(url):
    """Verify playlist/segment origins with Python TLS before the decoder reads them."""
    visited, origins = set(), set()
    def scan(address, depth):
        web(address)
        if address in visited: return
        if len(visited) >= 8 or depth > 3: raise ValueError('Playlist nesting exceeds limit')
        visited.add(address)
        text = update.read_bytes(address, {'User-Agent': UA}).decode('utf-8-sig', errors='replace')
        if not text.lstrip().startswith('#EXTM3U'): raise ValueError('Invalid HLS playlist')
        references = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith('#')]
        references += re.findall(r'URI="([^"]+)"', text)
        for value in references:
            child = web(urllib.parse.urljoin(address, value))
            parsed = urllib.parse.urlsplit(child)
            if parsed.path.lower().endswith('.m3u8'):
                scan(child, depth + 1)
            else:
                origin = (parsed.scheme, parsed.netloc)
                if origin in origins: continue
                if len(origins) >= 16: raise ValueError('Media origins exceed limit')
                # A denied HEAD still completes TLS verification; GET/decode is tested separately.
                request = urllib.request.Request(child, method='HEAD', headers={'User-Agent': UA})
                try:
                    with urllib.request.urlopen(request, timeout=10) as response: web(response.url)
                except urllib.error.HTTPError as response:
                    web(response.url); response.close()
                origins.add(origin)
    scan(url, 0)


def observe(binary, site, item, target):
    result = {'id': str(item.get('vod_id', '')), 'title': str(item.get('vod_name', ''))}
    try:
        detail = cms(site, ac='detail', ids=result['id']).get('list', [])
        current = next(v for v in detail if str(v.get('vod_id')) == result['id'])
        url = episode(current)
        if not url: raise ValueError('No HLS episode metadata')
        result['cover'] = cover(binary, current.get('vod_pic', ''))
        preflight(url)
        result['decode'] = decode(binary, url, target)
    except Exception as error:
        result['error'] = redact(type(error).__name__ + ': ' + str(error))
    return grade(result, target)


def review(binary, site):
    report = {'key': site['key'], 'name': site['name'], 'site': site, 'samples': []}
    try:
        items = samples(site)
        for item in items: report['samples'].append(observe(binary, site, item, 60))
        if len(items) == 2 and all(s['passed'] for s in report['samples']):
            report['samples'].append(observe(binary, site, items[0], 120))
    except Exception as error:
        report['error'] = redact(type(error).__name__ + ': ' + str(error))
    report['qualifies'] = qualifies(report)
    print(json.dumps({'key': site['key'], 'sample_count': len(report['samples']), 'qualifies': report['qualifies']}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    binary = shutil.which(args.ffmpeg)
    if not binary: raise RuntimeError('FFmpeg is required; no quality result was generated')
    out = args.output; old_report = update.load(out / 'automatic.json', None)
    health = update.load(out / 'health.json', {})
    previous = update.load(out / 'vod.json', {'sites': []})['sites']
    if not previous: raise ValueError('No last-known publication')
    candidates = [r['site'] for r in health.get('results', []) if r.get('ok')]
    full = args.force or due(old_report)
    if full:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            reports = list(pool.map(lambda site: review(binary, site), candidates))
        result = choose(reports, previous, (old_report or {}).get('state', {}))
        if not result['sites']: raise RuntimeError('No qualifying or last-known source; refusing empty publication')
        now = datetime.now(timezone.utc).isoformat()
        report = {'checked_at': now, 'attempted_epoch': time.time(), 'scope': SCOPE, 'policy': POLICY,
                  'sources': reports, 'state': result['state'], 'retained_keys': result['retained_keys'],
                  'retained_snapshot': result['retained_snapshot'], 'qualified_keys': [r['key'] for r in reports if r['qualifies']]}
        update.write(out / 'automatic.json', report)
        selection = update.load(out / 'selection.json', {})
        selection.update({'preferred_keys': result['keys'], 'last_attempt_at': now, 'retained_keys': result['retained_keys'],
                          'automatic_report': 'automatic.json', 'policy': POLICY})
        if report['qualified_keys']:
            selection.update({'checked_at': now, 'scope': SCOPE})
        update.write(out / 'selection.json', selection)
        update.write(out / 'vod.json', {'sites': result['sites'], 'parses': [], 'lives': []})
        health.update({'quality_attempted_at': now, 'quality_environment': SCOPE, 'published': len(result['sites']),
                       'retained_preferred_snapshot': result['retained_snapshot'], 'automatic_report': 'automatic.json'})
        update.write(out / 'health.json', health)
        print(json.dumps({'full_quality': True, 'qualified': len(report['qualified_keys']), 'published': len(result['sites']),
                          'retained_snapshot': result['retained_snapshot']}))
    else:
        observations = []
        for site in previous:
            try:
                item = cms(site, ac='detail', pg=1).get('list', [])[0]
                observations.append({'key': site['key'], 'cover': cover(binary, item.get('vod_pic', ''))})
            except Exception as error:
                observations.append({'key': site['key'], 'error': redact(type(error).__name__ + ': ' + str(error))})
        update.write(out / 'covers.json', {'checked_at': datetime.now(timezone.utc).isoformat(), 'scope': 'cover decode only', 'sources': observations})
        print(json.dumps({'full_quality': False, 'covers_checked': len(observations)}))


if __name__ == '__main__':
    main()
