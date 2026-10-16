"""Build the Varken Grafana dashboard: the original "Varken [Official]" dashboard, ported to Prometheus.

Writes dashboard/varken.json, which imports into any Grafana with a Prometheus data source (pick it in the
"Prometheus" variable). With --argus PATH it also writes the Argus copies, PATH/dashboards/media/varken.json
and varken-classic.json (the original dashboard's look), with Argus' pinned data source, uids and tags.
--check fails if a written file is out of date.

Run from the repository root:  python dashboard/make_dashboard.py [--argus ~/GitHub/Argus] [--check]
"""
import argparse
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DS = {'type': 'prometheus', 'uid': '${datasource}'}

DESCRIPTION = ("What's playing on Plex, what's in the libraries, and what Sonarr, Radarr, SickChill and Ombi are "
               "waiting on? The original Varken dashboard, on Varken's Prometheus metrics.")

# Library selectors. Grafana applies a variable's regex in the browser (JavaScript), so look-ahead works here.
LIBRARIES = {
    'movieslibrary': ('Movie libraries', 'movie', '/^(?!.*4k).*$/i'),
    'movies4klibrary': ('4K movie libraries', 'movie', '/4k/i'),
    'tvlibrary': ('TV libraries', 'show', '/^(?!.*4k).*$/i'),
    'tv4klibrary': ('4K TV libraries', 'show', '/4k/i'),
}


def library_items(variable, item):
    kind = LIBRARIES[variable][1]
    return f'varken_tautulli_library_items{{type="{kind}", library=~"${variable}", item="{item}"}}'


def added(variable, item):
    """Growth of the selected libraries over the dashboard's time range."""
    series = library_items(variable, item)
    return f'sum({series}) - sum(min_over_time({series}[$__range]))'


def target(expr, *, instant=True, table=False, legend=None):
    t = {'datasource': DS, 'expr': expr, 'refId': 'A', 'instant': instant, 'range': not instant}
    if table:
        t['format'] = 'table'
    if legend:
        t['legendFormat'] = legend
    return t


def stat(title, description, expr, grid, unit='none', no_value='Not reporting'):
    return {
        'type': 'stat', 'title': title, 'description': description, 'datasource': DS, 'gridPos': grid,
        'targets': [target(expr)],
        'fieldConfig': {'defaults': {'noValue': no_value, 'unit': unit, 'decimals': 0 if unit == 'none' else 1,
                                     'color': {'mode': 'fixed', 'fixedColor': 'text'}}, 'overrides': []},
        'options': {'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False},
                    'colorMode': 'value', 'graphMode': 'none', 'justifyMode': 'center', 'textMode': 'auto',
                    'orientation': 'auto'},
    }


def table(title, description, expr, grid, columns, sort=None, times=()):
    """One row per series; `columns` maps the labels to show, in order, to their headings. `times` are labels
    holding a date, shown as a time in the viewer's time zone."""
    conversions = [{'targetField': name, 'destinationType': 'time'} for name in times]
    return {
        'type': 'table', 'title': title, 'description': description, 'datasource': DS, 'gridPos': grid,
        'targets': [target(expr, table=True)],
        'transformations': [
            {'id': 'filterFieldsByName', 'options': {'include': {'names': list(columns)}}},
            *([{'id': 'convertFieldType', 'options': {'conversions': conversions, 'fields': {}}}] if times else []),
            {'id': 'organize', 'options': {'indexByName': {name: i for i, name in enumerate(columns)},
                                           'renameByName': columns}},
        ],
        'fieldConfig': {'defaults': {'custom': {'align': 'auto', 'minWidth': 80, 'cellOptions': {'type': 'auto'}}},
                        'overrides': [{'matcher': {'id': 'byName', 'options': columns[name]},
                                       'properties': [{'id': 'unit', 'value': 'time: MMM D HH:mm'}]}
                                      for name in times]},
        'options': {'showHeader': True, 'cellHeight': 'sm', 'footer': {'show': False},
                    'sortBy': [{'displayName': columns[sort or next(iter(columns))], 'desc': False}]},
    }


def pie(title, description, expr, legend, grid):
    return {
        'type': 'piechart', 'title': title, 'description': description, 'datasource': DS, 'gridPos': grid,
        'targets': [target(expr, legend=legend)],
        'fieldConfig': {'defaults': {'unit': 'none', 'decimals': 0, 'color': {'mode': 'palette-classic'}},
                        'overrides': []},
        'options': {'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False},
                    'pieType': 'donut', 'displayLabels': ['name'],
                    'legend': {'showLegend': True, 'displayMode': 'list', 'placement': 'bottom', 'values': ['value']},
                    'tooltip': {'mode': 'single', 'sort': 'none'}},
    }


def viewer_map(title, description, grid):
    return {
        'type': 'geomap', 'title': title, 'description': description, 'datasource': DS, 'gridPos': grid,
        'targets': [target('varken_tautulli_session_info{latitude!=""}', table=True)],
        'transformations': [{'id': 'convertFieldType', 'options': {'conversions': [
            {'targetField': 'latitude', 'destinationType': 'number'},
            {'targetField': 'longitude', 'destinationType': 'number'},
        ], 'fields': {}}}],
        'fieldConfig': {'defaults': {'color': {'mode': 'fixed', 'fixedColor': 'green'}}, 'overrides': []},
        'options': {
            'view': {'id': 'zero', 'lat': 0, 'lon': 0, 'zoom': 1, 'allLayers': True},
            'controls': {'showZoom': True, 'mouseWheelZoom': False, 'showAttribution': True},
            'basemap': {'type': 'default', 'name': 'Basemap', 'config': {}},
            'layers': [{
                'type': 'markers', 'name': 'Viewers', 'tooltip': True,
                'location': {'mode': 'coords', 'latitude': 'latitude', 'longitude': 'longitude'},
                'config': {'showLegend': False, 'style': {
                    'size': {'fixed': 8}, 'opacity': 0.7, 'color': {'fixed': 'green'},
                    'symbol': {'mode': 'fixed', 'fixed': 'img/icons/marker/circle.svg'},
                    'text': {'mode': 'field', 'field': 'location', 'fixed': ''},
                    'textConfig': {'fontSize': 11, 'offsetY': -12, 'textAlign': 'center', 'textBaseline': 'bottom'},
                }},
            }],
            'tooltip': {'mode': 'details'},
        },
    }


def streams_over_time(title, description, grid):
    return {
        'type': 'timeseries', 'title': title, 'description': description, 'datasource': DS, 'gridPos': grid,
        'targets': [target('sum(varken_tautulli_streams)', instant=False, legend='Streams')],
        'fieldConfig': {'defaults': {'unit': 'none', 'decimals': 0, 'min': 0, 'color': {'mode': 'palette-classic'},
                                     'custom': {'drawStyle': 'bars', 'fillOpacity': 60, 'lineWidth': 1,
                                                'barAlignment': 0, 'showPoints': 'never'}},
                        'overrides': []},
        'options': {'legend': {'showLegend': False, 'displayMode': 'list', 'placement': 'bottom'},
                    'tooltip': {'mode': 'single', 'sort': 'none'}},
        'interval': '1m',
    }


def g(x, y, w, h):
    return {'x': x, 'y': y, 'w': w, 'h': h}


def bandwidth(network):
    return f'sum(varken_tautulli_bandwidth_bytes_per_second{{network="{network}"}})'


def streams(decision):
    return f'sum(varken_tautulli_streams_by_decision{{decision="{decision}"}})'


def ombi(metric, status):
    return f'sum(varken_ombi_{metric}{{status="{status}"}})'


def panels():
    """The original dashboard's 35 panels: its layout below the stats, which are regrouped into wider tiles."""
    stream_details = ' Needs `stream_details = true` in Varken.'
    return [
        # Plex: streams and bandwidth.
        stat('Total Streams', 'Streams playing, paused or buffering now.', 'sum(varken_tautulli_streams)',
             g(0, 0, 3, 3)),
        stat('Transcodes', 'Streams Plex is transcoding.', streams('transcode'), g(3, 0, 3, 3)),
        stat('Direct Play', 'Streams playing the file as it is.', streams('direct_play'), g(6, 0, 3, 3)),
        stat('Direct Stream', 'Streams Plex remuxes without transcoding.', streams('direct_stream'), g(9, 0, 3, 3)),
        stat('Total BW', 'Bandwidth of the current streams.', bandwidth('total'), g(12, 0, 4, 3), 'Bps'),
        stat('LAN BW', 'Bandwidth of the streams to the local network.', bandwidth('lan'), g(16, 0, 4, 3), 'Bps'),
        stat('WAN BW', 'Bandwidth of the streams leaving the local network.', bandwidth('wan'), g(20, 0, 4, 3),
             'Bps'),
        # Libraries.
        stat('Movies', 'Movies in the movie libraries.', f'sum({library_items("movieslibrary", "total")})',
             g(0, 3, 3, 3)),
        stat('TV Shows', 'Shows in the TV libraries.', f'sum({library_items("tvlibrary", "total")})', g(3, 3, 3, 3)),
        stat('TV Seasons', 'Seasons in the TV libraries.', f'sum({library_items("tvlibrary", "seasons")})',
             g(6, 3, 3, 3)),
        stat('TV Episodes', 'Episodes in the TV libraries.', f'sum({library_items("tvlibrary", "episodes")})',
             g(9, 3, 3, 3)),
        stat('4K Movies', 'Movies in the 4K movie libraries.', f'sum({library_items("movies4klibrary", "total")})',
             g(12, 3, 3, 3), no_value='No library'),
        stat('4K TV Shows', 'Shows in the 4K TV libraries.', f'sum({library_items("tv4klibrary", "total")})',
             g(15, 3, 3, 3), no_value='No library'),
        stat('4K TV Seasons', 'Seasons in the 4K TV libraries.', f'sum({library_items("tv4klibrary", "seasons")})',
             g(18, 3, 3, 3), no_value='No library'),
        stat('4K TV Episodes', 'Episodes in the 4K TV libraries.',
             f'sum({library_items("tv4klibrary", "episodes")})', g(21, 3, 3, 3), no_value='No library'),
        # Ombi, and what the libraries gained.
        stat('Req. Pending', 'Ombi requests waiting for approval.', ombi('requests', 'pending'), g(0, 6, 3, 3)),
        stat('Req. Approved', 'Ombi requests approved but not yet available.', ombi('requests', 'approved'),
             g(3, 6, 3, 3)),
        stat('Req. Completed', 'Ombi requests now available.', ombi('requests', 'available'), g(6, 6, 3, 3)),
        stat('Issues Pending', 'Ombi issues nobody has picked up.', ombi('issues', 'pending'), g(9, 6, 3, 3)),
        stat('Issues Ongoing', 'Ombi issues being worked on.', ombi('issues', 'in_progress'), g(12, 6, 3, 3)),
        stat('Issues Resolved', 'Ombi issues resolved.', ombi('issues', 'resolved'), g(15, 6, 3, 3)),
        stat('Movies Added', 'How many more movies the movie libraries hold than at their lowest in the '
             "dashboard's time range.", added('movieslibrary', 'total'), g(18, 6, 3, 3)),
        stat('Episodes Added', 'How many more episodes the TV libraries hold than at their lowest in the '
             "dashboard's time range.", added('tvlibrary', 'episodes'), g(21, 6, 3, 3)),
        # Middle: what's playing, the queues and the map.
        pie('Device Types', "Current sessions by the player's platform.",
            'sum by (platform) (varken_tautulli_sessions)', '{{platform}}', g(0, 9, 4, 8)),
        pie('Stream Types', 'Current sessions by video decision (direct play, copy, transcode).',
            'sum by (video_decision) (varken_tautulli_sessions)', '{{video_decision}}', g(4, 9, 4, 8)),
        table('Movies in Queue', "Movies in Radarr's download queue.", 'varken_radarr_queue_item_info',
              g(8, 9, 8, 4), {'movie': 'Movie', 'quality': 'Quality', 'protocol': 'Protocol'}),
        viewer_map('Viewer Locations', "Where the current viewers are, from the GeoLite2 city of each viewer's "
                   'address. Viewers who can\'t be placed are left out.' + stream_details, g(16, 9, 8, 10)),
        table('TV Shows in Queue', "Episodes in Sonarr's download queue.", 'varken_sonarr_queue_item_info',
              g(8, 13, 8, 4), {'series': 'Series', 'episode': 'Episode', 'title': 'Title', 'protocol': 'Protocol'}),
        streams_over_time('Server Popularity', 'Streams over time.', g(0, 17, 16, 5)),
        table('TV Shows on Today (Sonarr)', "Episodes airing from today through Sonarr's `future_days` (1 by "
              'default: today and tomorrow).', 'varken_sonarr_episode_info{kind="future"}', g(16, 19, 8, 5),
              {'airs': 'Airs', 'series': 'Series', 'episode': 'Episode', 'title': 'Title',
               'downloaded': 'Downloaded'}, times=['airs']),
        table('Users Online', 'Who is watching what, how, and from where.' + stream_details,
              'varken_tautulli_session_info', g(0, 22, 16, 7),
              {'friendly_name': 'User', 'title': 'Media', 'state': 'State', 'quality': 'Quality',
               'video_decision': 'Decision', 'quality_profile': 'Profile', 'platform': 'Platform',
               'product_version': 'Version', 'location': 'Location'}),
        table('TV Shows (SickChill)', "SickChill's coming episodes, and the ones it missed.",
              'varken_sickchill_episode_info', g(16, 24, 8, 4),
              {'airdate': 'Air date', 'show': 'Show', 'episode': 'Episode', 'status': 'Status'}),
        table('Missing Available Movies', 'Monitored movies Radarr has no file for, though they are out.',
              'varken_radarr_missing_info{available="true"}', g(16, 28, 8, 5), {'movie': 'Movie'}),
        table('Ombi Requests Pending', 'Ombi requests not yet available or denied. The requester is shown only '
              'with `stream_details = true` in Varken.', 'varken_ombi_request_info{status=~"pending|approved"}',
              g(0, 29, 16, 9), {'requested': 'Requested', 'title': 'Title', 'type': 'Type', 'status': 'Status',
                                'user': 'Requested by'}, sort='requested', times=['requested']),
        table('Missing TV Shows (Last 7 Days)', "Monitored episodes without a file that aired in Sonarr's last "
              '`missing_days` (7 by default).', 'varken_sonarr_episode_info{kind="missing"}', g(16, 33, 8, 5),
              {'airs': 'Aired', 'series': 'Series', 'episode': 'Episode', 'title': 'Title'}, times=['airs']),
    ]


def library_variable(name):
    label, kind, regex = LIBRARIES[name]
    query = f'label_values(varken_tautulli_library_items{{type="{kind}"}}, library)'
    return {
        'name': name, 'label': label, 'type': 'query', 'datasource': DS, 'definition': query,
        'query': {'query': query, 'refId': name}, 'regex': regex, 'refresh': 2, 'sort': 1,
        'includeAll': True, 'multi': True, 'current': {'text': ['All'], 'value': ['$__all']}, 'options': [],
        'hide': 0,
    }


def dashboard():
    """The importable dashboard, with a data source variable."""
    built = panels()
    for i, panel in enumerate(built, 1):
        panel['id'] = i
    return {
        'id': None, 'uid': 'varken', 'title': 'Varken', 'description': DESCRIPTION,
        'tags': ['varken', 'plex', 'prometheus'], 'editable': True, 'graphTooltip': 1,
        'time': {'from': 'now-24h', 'to': 'now'}, 'refresh': '1m', 'timezone': 'browser', 'schemaVersion': 41,
        'version': 1, 'annotations': {'list': []}, 'links': [],
        'templating': {'list': [
            {'name': 'datasource', 'label': 'Prometheus', 'type': 'datasource', 'query': 'prometheus',
             'current': {}, 'options': [], 'refresh': 1, 'hide': 0},
            *(library_variable(name) for name in LIBRARIES),
        ]},
        'panels': built,
    }


def pin_datasource(node, uid):
    """Replace the data source variable with a fixed uid, everywhere."""
    if isinstance(node, dict):
        return {key: ({'type': 'prometheus', 'uid': uid} if value == DS else pin_datasource(value, uid))
                for key, value in node.items()}
    if isinstance(node, list):
        return [pin_datasource(item, uid) for item in node]
    return node


# Services the owner doesn't run: Argus' copy has none of their panels.
ARGUS_WITHOUT = ('varken_ombi_', 'varken_sickchill_')
def seerr(metric, status):
    return f'sum(varken_seerr_{metric}{{status="{status}"}})'


def seerr_panels():
    """Seerr in the Ombi panels' places, for Argus (which runs Seerr, not Ombi)."""
    return [
        stat('Req. Pending', 'Seerr requests waiting for approval.', seerr('requests', 'pending'), g(0, 6, 3, 3)),
        stat('Req. Processing', 'Seerr requests approved and not in the library yet.',
             seerr('requests', 'processing'), g(3, 6, 3, 3)),
        stat('Req. Available', 'Seerr requests now in the library.', seerr('requests', 'available'),
             g(6, 6, 3, 3)),
        stat('Req. Declined', 'Seerr requests declined.', seerr('requests', 'declined'), g(9, 6, 3, 3)),
        stat('Issues Open', 'Seerr issues still open.', seerr('issues', 'open'), g(12, 6, 3, 3)),
        stat('Issues Closed', 'Seerr issues resolved.', seerr('issues', 'closed'), g(15, 6, 3, 3)),
        table('Requests Waiting (Seerr)', 'Seerr requests pending approval, or approved and not in the library yet '
              '(the 100 newest). The requester is shown only with `stream_details = true` in Varken.',
              'varken_seerr_request_info', g(0, 29, 16, 9),
              {'requested': 'Requested', 'title': 'Title', 'type': 'Type', 'is4k': '4K', 'status': 'Status',
               'user': 'Requested by'}, sort='requested', times=['requested']),
    ]


def lidarr_panels():
    """Lidarr's queue and its missing and upcoming albums, for Argus (the original dashboard had no Lidarr)."""
    return [
        table('Music in Queue', "Releases in Lidarr's download queue.", 'varken_lidarr_queue_item_info',
              g(0, 38, 8, 6), {'artist': 'Artist', 'album': 'Album', 'release': 'Release', 'quality': 'Quality',
                               'protocol': 'Protocol'}),
        table('Missing Albums', "Monitored albums released in Lidarr's last `missing_days` without every track.",
              'varken_lidarr_album_info{kind="missing"}', g(8, 38, 8, 6),
              {'released': 'Released', 'artist': 'Artist', 'album': 'Album', 'tracks': 'Tracks'},
              sort='released', times=['released']),
        table('Albums Coming Out', "Albums coming out from today through Lidarr's `future_days`.",
              'varken_lidarr_album_info{kind="future"}', g(16, 38, 8, 6),
              {'released': 'Released', 'artist': 'Artist', 'album': 'Album', 'tracks': 'Tracks'},
              sort='released', times=['released']),
    ]


# Argus reads Sonarr and Radarr as server 1 and their 4K instances as server 2 (its compose file), so its copy's
# Sonarr and Radarr tables say which instance each row is from.
ARGUS_INSTANCES = {'1': 'HD', '2': '4K'}


def with_instance_column(panel):
    """Add an Instance column, first, naming the server a Sonarr or Radarr table row comes from."""
    include = panel['transformations'][0]['options']['include']['names']
    include.insert(0, 'server')
    organize = panel['transformations'][-1]['options']
    organize['indexByName'] = {name: i for i, name in enumerate(include)}
    organize['renameByName'] = {'server': 'Instance', **organize['renameByName']}
    panel['fieldConfig']['overrides'].append({
        'matcher': {'id': 'byName', 'options': 'Instance'},
        'properties': [
            {'id': 'mappings', 'value': [{'type': 'value', 'options': {
                server: {'text': name, 'index': i} for i, (server, name) in enumerate(ARGUS_INSTANCES.items())}}]},
            {'id': 'custom.width', 'value': 80},
        ],
    })


def uses(panel, prefix):
    return any(prefix in target['expr'] for target in panel['targets'])


def argus_dashboard():
    """Argus' copy: its provisioned data source, uid and tags, and the link to its other dashboards. The owner runs
    neither Ombi nor SickChill, so their panels are left out; Seerr's take Ombi's places."""
    dash = pin_datasource(copy.deepcopy(dashboard()), 'prometheus')
    dash['panels'] = [panel for panel in dash['panels'] if not any(uses(panel, prefix) for prefix in ARGUS_WITHOUT)]
    for panel in dash['panels']:
        if panel['type'] == 'table' and (uses(panel, 'varken_sonarr_') or uses(panel, 'varken_radarr_')):
            with_instance_column(panel)
    # Seerr where Ombi was, and Lidarr below, numbered after the original 35 panels.
    added = seerr_panels() + lidarr_panels()
    for number, panel in enumerate(pin_datasource(added, 'prometheus'), len(dashboard()['panels']) + 1):
        panel['id'] = number
        dash['panels'].append(panel)
    dash.update(uid='argus-varken', tags=['argus', 'media', 'varken'], links=[{
        'title': 'Argus dashboards', 'type': 'dashboards', 'tags': ['argus'], 'asDropdown': True,
        'includeVars': False, 'keepTime': True, 'targetBlank': False, 'icon': 'external link'}])
    dash['templating']['list'] = [v for v in dash['templating']['list'] if v['name'] != 'datasource']
    return dash


# The original "Varken [Official]" look, for Argus' classic copy: the upstream grid, tiles with solid backgrounds and
# their titles inside, rows coloured by status, a heat strip for Server Popularity, a dark map of the US.
CLASSIC_TILES = {
    # title: (colour, upstream grid x, y)
    'Total BW': ('#508642', 1, 0), 'LAN BW': ('#508642', 3, 0), 'WAN BW': ('#508642', 5, 0),
    'Req. Pending': ('#299c46', 8, 0), 'Req. Processing': ('#299c46', 10, 0), 'Req. Available': ('#299c46', 12, 0),
    'Movies Added': ('#967302', 14, 0), 'Movies': ('#584477', 16, 0), 'TV Shows': ('#584477', 18, 0),
    'TV Seasons': ('#584477', 20, 0), 'TV Episodes': ('#584477', 22, 0),
    'Total Streams': ('rgb(8, 125, 161)', 0, 2), 'Transcodes': ('rgb(8, 125, 161)', 2, 2),
    'Direct Play': ('rgb(8, 125, 161)', 4, 2), 'Direct Stream': ('rgb(8, 125, 161)', 6, 2),
    'Issues Open': ('#299c46', 8, 2), 'Issues Closed': ('#299c46', 10, 2), 'Req. Declined': ('#299c46', 12, 2),
    'Episodes Added': ('#967302', 14, 2), '4K Movies': ('#584477', 16, 2), '4K TV Shows': ('#584477', 18, 2),
    '4K TV Seasons': ('#584477', 20, 2), '4K TV Episodes': ('#584477', 22, 2),
}
CLASSIC_TITLES = {'Transcodes': 'Transcode Streams', 'Direct Play': 'Direct Play Streams',
                  'Req. Processing': 'Requests Processing', 'Req. Available': 'Requests Completed',
                  'Req. Declined': 'Requests Declined', 'Movies Added': 'Recently Added Movies',
                  'Episodes Added': 'Recently Added TV'}
CLASSIC_GRID = {
    'Device Types': g(0, 4, 4, 8), 'Stream Types': g(4, 4, 4, 8), 'Movies in Queue': g(8, 4, 8, 4),
    'Viewer Locations': g(16, 4, 8, 10), 'TV Shows in Queue': g(8, 8, 8, 4), 'Server Popularity': g(0, 12, 16, 5),
    'TV Shows on Today (Sonarr)': g(16, 14, 8, 5), 'Users Online': g(0, 17, 16, 7),
    'Missing Available Movies': g(16, 19, 8, 5), 'Requests Waiting (Seerr)': g(0, 24, 16, 9),
    'Missing TV Shows (Last 7 Days)': g(16, 24, 8, 5),
    'Music in Queue': g(0, 33, 8, 6), 'Missing Albums': g(8, 33, 8, 6), 'Albums Coming Out': g(16, 33, 8, 6),
}
# The original's device colours.
DEVICE_COLOURS = {'Android': '#a4ca39', 'Chrome': '#db3236', 'Chromecast': '#039BE5', 'NetCast': '#c8135c',
                  'Playstation 4': '#003791', 'Plex Media Player': '#e67817', 'Roku': '#6d3c97', 'Samsung': '#034ea2',
                  'Tizen': '#034ea2', 'Xbox One': '#107c10', 'iOS': '#858487', 'tvOS': '#858487'}


def colour_rows_by(panel, field, colours):
    """Colour each row of a table by one column's value (value -> colour); other values keep the default."""
    heading = panel['transformations'][-1]['options']['renameByName'].get(field, field)
    panel['fieldConfig']['overrides'].append({
        'matcher': {'id': 'byName', 'options': heading},
        'properties': [
            {'id': 'mappings', 'value': [{'type': 'value', 'options': {
                value: {'color': colour, 'index': i} for i, (value, colour) in enumerate(colours.items())}}]},
            {'id': 'custom.cellOptions', 'value': {'type': 'color-background', 'mode': 'basic', 'applyToRow': True}},
        ],
    })


def colour_rows(panel, colour):
    """Every row of a table in one colour."""
    defaults = panel['fieldConfig']['defaults']
    defaults['color'] = {'mode': 'fixed', 'fixedColor': colour}
    defaults['custom']['cellOptions'] = {'type': 'color-background', 'mode': 'basic'}


def classic_tile(panel):
    colour, x, y = CLASSIC_TILES[panel['title']]
    title = CLASSIC_TITLES.get(panel['title'], panel['title'])
    defaults = panel['fieldConfig']['defaults']
    defaults['color'] = {'mode': 'fixed', 'fixedColor': colour}
    defaults['displayName'] = title
    if defaults['unit'] == 'Bps':  # the original showed bits per second
        panel['targets'][0]['expr'] = f"{panel['targets'][0]['expr']} * 8"
        defaults['unit'] = 'bps'
    panel.update(title='', gridPos=g(x, y, 2, 2), transparent=False)
    panel['options'].update(colorMode='background_solid', textMode='value_and_name', justifyMode='center',
                            text={'titleSize': 12})
    panel['description'] = f"{title}: {panel['description']}"


def classic_dashboard():
    """Argus' copy in the original dashboard's look: same queries (plus the week-long pies), restyled."""
    dash = copy.deepcopy(argus_dashboard())
    dash.update(uid='argus-varken-classic', title='Varken [Classic]',
                description=DESCRIPTION + ' The original dashboard\'s look.')
    for panel in dash['panels']:
        title = panel['title']
        if panel['type'] == 'stat':
            classic_tile(panel)
            continue
        panel['gridPos'] = CLASSIC_GRID[title]
        if panel['type'] == 'piechart':
            # Over the last week, as the original: average concurrent sessions by platform or decision.
            by = 'platform' if title == 'Device Types' else 'video_decision'
            panel['targets'][0]['expr'] = f'sum by ({by}) (avg_over_time(varken_tautulli_sessions[$__range]))'
            panel['timeFrom'] = '7d'
            panel['options'].update(displayLabels=['name', 'percent'],
                                    legend={'showLegend': False, 'displayMode': 'list', 'placement': 'right'})
            if by == 'platform':
                panel['fieldConfig']['overrides'] = [
                    {'matcher': {'id': 'byName', 'options': name},
                     'properties': [{'id': 'color', 'value': {'mode': 'fixed', 'fixedColor': colour}}]}
                    for name, colour in DEVICE_COLOURS.items()]
        elif panel['type'] == 'timeseries':  # Server Popularity: the original's heat strip
            panel['type'] = 'status-history'
            panel['interval'] = '1m'
            panel['fieldConfig'] = {'defaults': {'color': {'mode': 'continuous-BlYlRd'}, 'min': 0,
                                                 'custom': {'lineWidth': 0, 'fillOpacity': 90}},
                                    'overrides': []}
            panel['options'] = {'showValue': 'never', 'rowHeight': 1, 'colWidth': 1,
                                'legend': {'showLegend': False}, 'tooltip': {'mode': 'single', 'sort': 'none'}}
        elif panel['type'] == 'geomap':
            panel['options']['view'] = {'id': 'coords', 'lat': 37.9, 'lon': -94.9, 'zoom': 4, 'allLayers': True}
            panel['options']['basemap'] = {'type': 'carto', 'name': 'Basemap',
                                           'config': {'theme': 'dark', 'showLabels': True}}
            panel['fieldConfig']['defaults']['color'] = {'mode': 'fixed', 'fixedColor': '#24c3ff'}
            panel['options']['layers'][0]['config']['style'].update(size={'fixed': 5},
                                                                     color={'fixed': '#24c3ff'})
        elif title in ('Movies in Queue', 'TV Shows in Queue', 'Music in Queue'):
            colour_rows_by(panel, 'protocol', {'usenet': '#629e51', 'torrent': 'rgb(168, 147, 4)'})
        elif title == 'TV Shows on Today (Sonarr)':
            colour_rows_by(panel, 'downloaded', {'false': '#0a50a1', 'true': '#24c3ff'})
        elif title == 'Users Online':
            colour_rows_by(panel, 'state', {'playing': '#3f6833', 'paused': 'rgb(8, 125, 161)',
                                            'buffering': 'rgb(168, 147, 4)'})
        elif title == 'Requests Waiting (Seerr)':
            colour_rows_by(panel, 'status', {'pending': '#052b51', 'processing': '#967302'})
        elif title in ('Missing TV Shows (Last 7 Days)', 'Missing Albums'):
            colour_rows(panel, '#bf1b00')
        elif title == 'Albums Coming Out':
            colour_rows(panel, '#0a50a1')
    return dash


def formatted(dash):
    """As Grafana exports a dashboard: 2-space indent, trailing newline."""
    return json.dumps(dash, indent=2) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--argus', type=Path, help='an Argus checkout to write the Argus copy into')
    parser.add_argument('--check', action='store_true', help="fail if a file isn't up to date; write nothing")
    args = parser.parse_args(argv)
    outputs = [(HERE / 'varken.json', dashboard())]
    if args.argus:
        media = args.argus.expanduser() / 'dashboards' / 'media'
        outputs.append((media / 'varken.json', argus_dashboard()))
        outputs.append((media / 'varken-classic.json', classic_dashboard()))
    stale = []
    for path, dash in outputs:
        text = formatted(dash)
        if args.check:
            if not path.is_file() or path.read_text() != text:
                stale.append(path)
        else:
            path.write_text(text)
            print(f'wrote {path}')
    for path in stale:
        print(f'{path} is out of date: run python dashboard/make_dashboard.py', file=sys.stderr)
    return 1 if stale else 0


if __name__ == '__main__':
    sys.exit(main())
