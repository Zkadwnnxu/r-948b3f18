# Configuration

Public endpoint configuration and metadata checks.

Data: https://raw.githubusercontent.com/Zkadwnnxu/r-948b3f18/data/vod.json

Status: https://raw.githubusercontent.com/Zkadwnnxu/r-948b3f18/data/health.json

The data branch contains the published files. The catalog lists reviewed HTTP endpoints and their reference pages. The updater requests metadata only, retains previous entries during temporary failures, and does not run external code.

Maintenance is scheduled every six hours after the pending maintenance PR is reviewed and merged. Before that, the published data is available but automatic maintenance is not active.

Local checks: `python3 -m unittest discover -s tests -v`.

This public repository contains no application source, credentials or user data. A public URL does not provide access control.
