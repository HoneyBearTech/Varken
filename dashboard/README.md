# Varken dashboard

[`varken.json`](varken.json) is the original "Varken [Official]" Grafana dashboard ported to Varken's
Prometheus metrics. It has the same 35 panels, laid out as in the original below the numbers at the top, but
uses Grafana's built-in panels: the original needed the Angular singlestat, piechart and worldmap plugins,
which current Grafana no longer runs.

## Importing it

Needs Grafana 12 or later (tested with 13) and a Prometheus that scrapes Varken ([installing](../docs/installing.md)).

1. In Grafana, **Dashboards → New → Import**, then upload `varken.json`.
2. Pick your Prometheus data source in the **Prometheus** variable at the top.
3. Pick your libraries in the **Movie libraries**, **4K movie libraries**, **TV libraries** and **4K TV
   libraries** variables. By default, libraries whose name contains "4K" go in the 4K panels and every
   other library goes in the others.

## What needs what

| Panels | Need |
| --- | --- |
| Bandwidth, streams, Device Types, Stream Types, Server Popularity, library counts | Tautulli, with `get_activity` and `get_stats` on |
| Users Online, Viewer Locations | Tautulli, and `[prometheus] stream_details = true`: these show who is watching what and from where ([security](../docs/security.md)). The map also needs GeoIP (a MaxMind license key) |
| Movies in Queue, Missing Available Movies | Radarr 4 or later, with `queue` and `get_missing` on |
| TV Shows in Queue, TV Shows on Today, Missing TV Shows | Sonarr 4 or later, with `queue`, `future_days` and `missing_days` on |
| TV Shows (SickChill) | SickChill, with `get_missing` on |
| Requests, issues, Ombi Requests Pending | Ombi, with `request_total_counts`, `issue_status_counts` and `request_type_counts` on; the requester only with `stream_details = true` |

A panel whose service isn't set up shows "Not reporting" or an empty table.

Differences from the original:

- The numbers at the top are in three rows of wider tiles (Plex streams and bandwidth, libraries, Ombi), with
  shorter titles, instead of the original's two rows of small ones.
- "Movies Added" and "Episodes Added" (the original's "Recently Added" panels) show how much the libraries
  grew over the dashboard's time range, from the library counts. The original counted distinct values in
  InfluxDB.
- The 4K panels say "No library" when no library matches the 4K variables.
- Server Popularity is a bar chart of streams over time, not a heatmap.
- Bandwidth is in bytes per second.
- There are no links to the Ombi, Sonarr, Radarr and Tautulli web pages.
- There is no server filter: every panel adds up all the servers Varken reads.

## Changing it

The JSON is generated. Edit [`make_dashboard.py`](make_dashboard.py) and run, from the repository root:

```sh
python dashboard/make_dashboard.py                        # writes dashboard/varken.json
python dashboard/make_dashboard.py --argus ~/GitHub/Argus # also writes Argus' copy
```

CI checks that `varken.json` matches the generator, and that every query uses only metrics and labels Varken
serves (`tests/test_dashboard.py`).
