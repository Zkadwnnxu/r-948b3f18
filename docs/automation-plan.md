# Scheduled quality maintenance

Goal: keep the existing data/vod.json URL and neutral repository identity while enabling source maintenance authorized by the user.

1. Extend metadata reads with a bounded byte reader reused for covers. Add a standard-library quality worker with null-output video+audio decoding, per-process deadlines, redacted logs and no devices/windows. Keep two 60-second baselines plus a 120-second confirmation and the existing thresholds.
2. Add offline selection/retention/deadline tests first; prove owned media and TLS positive/negative controls in cloud only. Every six hours check metadata and preferred covers; every 24 hours, or explicitly requested, run full quality review. Newly available sources cannot enter the default file on metadata alone.
3. Preserve last-known sources briefly on individual failures; record stale entries. If a full cloud run yields no qualifying source, keep the previous nonempty publication and explicitly mark it as retained. Cloud observations are labelled as cloud results, not TV or Windows measurements.
4. Run one whole-change static review, fix important findings and verify. The user explicitly authorizes merge of resource PR1 and activation; this does not authorize merging software PRs.
5. Merge, verify enabled workflow configuration, observe its first full run, and compare anonymous JSON bytes with the data commit. Keep descriptions/topics neutral and do not expose media URLs or credentials in reports.

No local playback, FFmpeg jobs, emulator use, application changes, version changes or signing.
