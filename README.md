# Configuration

Data: https://raw.githubusercontent.com/Zkadwnnxu/r-948b3f18/data/vod.json

The data branch contains the publication, prior full catalog, observations and selection. No application source, credentials or user data is stored here. Public URLs do not provide access control.

The scheduled job checks metadata and covers every six hours. A complete quality review runs when the last full attempt is at least 24 hours old; manual dispatch and maintenance-code changes can force a full review. It decodes audio/video to null only, with no display or audio devices.

New or recovered entries need two 60-second baselines and a 120-second confirmation, normal covers, audio/video decoding without errors, bounded progress gaps and prompt first frames. The numeric thresholds are stored with each report. Passing entries are ordered by median first-frame time. No metadata-only response can promote an unreviewed entry.

Individual failed sources have up to two review rounds of grace and are marked retained. Three consecutive failures remove them when other valid entries remain. A completely failed run preserves the previous nonempty publication and explicitly reports retention. Cloud results are dated observations of that runner/network, not a TV-device or long-term guarantee.

Files: `vod.json` is the current publication; `all.json` retains the original 14-entry snapshot; `playback.json` retains the original computer sample review; `automatic.json` records the latest complete cloud attempt; `covers.json` records light cover checks. `selection.json` records the publication policy and retained keys. Metadata-only reports never replace the historical playback evidence.

Local checks: `python3 -m unittest discover -s tests -v`. Cloud owned positive/negative controls must pass before maintenance can publish. The workflow only commits generated files to `data`, never code to `main`.
