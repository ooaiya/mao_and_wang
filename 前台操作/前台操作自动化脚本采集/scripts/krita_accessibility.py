#!/usr/bin/env python3
"""Fresh, read-only AT-SPI query for the exact owned Krita PID. No OCR/input."""
import argparse
from collections import deque
import json
import re


class AccessibilityPending(RuntimeError):
    retryable = True

    def __init__(self, message, candidates=()):
        super().__init__(message)
        self.candidates = list(candidates)


class AccessibilityAmbiguous(AccessibilityPending):
    retryable = False


def child_count(node):
    count = node.childCount
    if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 10000:
        raise RuntimeError('invalid Accessible childCount')
    return count


def live_state(node, api):
    state = node.getState()
    if state is None or (hasattr(api, 'STATE_DEFUNCT') and state.contains(api.STATE_DEFUNCT)):
        raise RuntimeError('Accessible proxy is defunct')
    return state


def children(node, count):
    # Index every advertised child. A disconnected/partial tree is not empty.
    result = [node.getChildAtIndex(i) for i in range(count)]
    if any(child is None for child in result):
        raise RuntimeError('Accessible child unavailable')
    return result


def read_tree(app, api, root_count):
    tables, dialogs, gui_nodes = [], [], []
    queue = deque((child, [], None, 1, frozenset()) for child in children(app, root_count))
    visited = 0
    while queue:
        node, ancestors, dialog, depth, trail = queue.popleft()
        visited += 1
        if visited > 10000 or depth > 32:
            raise RuntimeError('AT-SPI树超过诊断上限')
        identity = (getattr(node, 'bus_name', ''), getattr(node, 'path', None))
        key = identity if identity[1] is not None else ('proxy', id(node))
        if key in trail:
            raise RuntimeError('AT-SPI child tree contains a cycle')
        trail = trail | {key}
        # Do not swallow stale-proxy/tree exceptions and select a partial tree.
        name = node.name or ''
        role = node.getRole()
        role_name = node.getRoleName()
        state = live_state(node, api)
        showing = state.contains(api.STATE_SHOWING)
        count = child_count(node)
        current = children(node, count)
        context = ancestors + [name]
        details = dict(name=name, role=role_name, path=identity[1], childCount=count)
        if showing and role != api.ROLE_APPLICATION and count > 0:
            gui_nodes.append(details)
        if role in (api.ROLE_DIALOG, api.ROLE_FILE_CHOOSER, api.ROLE_ALERT) and showing:
            dialog = dict(name=name, text=[], buttons=[])
            dialogs.append(dialog)
        if dialog is not None and name:
            dialog['text'].append(name)
        if role == api.ROLE_PUSH_BUTTON and showing and dialog is not None:
            rect = node.queryComponent().getExtents(api.DESKTOP_COORDS)
            dialog['buttons'].append(dict(name=name, box=[rect.x, rect.y, rect.width, rect.height]))
        if role in (api.ROLE_TREE, api.ROLE_TREE_TABLE, api.ROLE_TABLE) and showing:
            labelled = []
            for relation in node.getRelationSet():
                if relation.getRelationType() == api.RELATION_LABELLED_BY:
                    labelled.extend(relation.getTarget(i).name or '' for i in range(relation.getNTargets()))
            if re.search(r'\bLayers\b|图层|圖層', ' / '.join(context + labelled), re.I):
                try:
                    rows = node.queryTable().nRows
                except NotImplementedError:
                    rows = None  # A visible tree can exist without a Table interface.
                if rows is not None:
                    if not isinstance(rows, int) or isinstance(rows, bool) or rows < 0:
                        raise RuntimeError('invalid Layers row count')
                    tables.append(dict(name=name, context=context, row_count=rows))
        queue.extend((child, context, dialog, depth + 1, trail) for child in current)
    return dict(layer_views=tables, dialogs=dialogs, gui_nodes=gui_nodes, visited=visited)


def snapshot(pid):
    import pyatspi
    if type(pid) is not int or pid <= 1:
        raise ValueError('exact owned PID required')
    # Never cache Desktop, Application or descendant proxies between calls.
    desktop = pyatspi.Registry.getDesktop(0)
    candidates, valid, uncertain = [], [], False
    try:
        apps = children(desktop, child_count(desktop))
    except Exception as error:
        raise AccessibilityPending('AT-SPI Desktop读取失败：' + repr(error)) from error
    for index, app in enumerate(apps):
        record = dict(index=index, name=None, pid=None, role=None, path=None,
                      bus_name=None, childCount=None, selection='unreadable')
        candidates.append(record)
        # Diagnostic reads are independent: retain the other fields if one fails.
        failures = []
        for field, getter in (
            ('pid', lambda: app.get_process_id()), ('name', lambda: app.name or ''),
            ('role', lambda: app.getRoleName()), ('path', lambda: app.path),
            ('bus_name', lambda: getattr(app, 'bus_name', '')),
            ('childCount', lambda: child_count(app)),
        ):
            try:
                record[field] = getter()
            except Exception as error:
                failures.append(field + ': ' + repr(error))
        if failures:
            record['diagnostics'] = failures
        if not isinstance(record['pid'], int) or isinstance(record['pid'], bool) or record['pid'] != pid:
            record['selection'] = 'rejected_pid'
            continue
        try:
            record['role_id'] = int(app.getRole())
            if record['role_id'] != pyatspi.ROLE_APPLICATION:
                record['selection'] = 'rejected_role'
                continue
            if failures:
                raise RuntimeError('; '.join(failures))
            if record['childCount'] == 0:
                record['selection'] = 'rejected_empty'
                continue
            live_state(app, pyatspi)
            tree = read_tree(app, pyatspi, record['childCount'])
            if not tree['gui_nodes']:
                record['selection'] = 'rejected_no_visible_gui_tree'
                continue
            # A proxy can disconnect while traversing. Revalidate the root.
            if (app.get_process_id() != pid or app.getRole() != pyatspi.ROLE_APPLICATION
                    or child_count(app) != record['childCount']):
                raise RuntimeError('Application changed during tree inspection')
            live_state(app, pyatspi)
            record['selection'] = 'valid_gui_tree'
            record['visited'] = tree['visited']
            valid.append((record, tree))
        except Exception as error:
            record.update(selection='retry_tree_unavailable', error=repr(error))
            uncertain = True
    if len(valid) > 1:
        raise AccessibilityAmbiguous('AT-SPI同PID存在多个有效Application界面树', candidates)
    if uncertain:
        raise AccessibilityPending('AT-SPI同PID对象失效或界面树未完整读取，重新查询', candidates)
    if not valid:
        raise AccessibilityPending('AT-SPI没有匹配本轮PID的有效Application界面树', candidates)
    selected, tree = valid[0]
    selected['selection'] = 'selected'
    return dict(schema_version=1, ok=True, pid=pid, candidates=candidates,
                selected_application=dict(selected), **tree)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--pid', type=int)
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--expect-layers', type=int, help='read-only check; does not open files or issue GUI input')
    args = parser.parse_args(argv)
    try:
        if args.probe:
            if args.expect_layers is not None:
                raise ValueError('--expect-layers requires --pid')
            import pyatspi
            desktop = pyatspi.Registry.getDesktop(0)
            result = dict(schema_version=1, ok=True, desktop_children=child_count(desktop))
        elif args.pid is not None:
            result = snapshot(args.pid)
            if args.expect_layers is not None:
                views = result['layer_views']
                verified = len(views) == 1 and views[0]['row_count'] == args.expect_layers
                result['layers_validation'] = dict(expected=args.expect_layers, unique=len(views) == 1, passed=verified)
                if not verified:
                    result.update(ok=False, retryable=False, error='没有唯一且数量符合预期的Layers表')
        else:
            raise ValueError('exact PID or --probe required')
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['ok'] else 1
    except Exception as error:
        print(json.dumps(dict(schema_version=1, ok=False, pid=args.pid,
                              retryable=getattr(error, 'retryable', False),
                              candidates=getattr(error, 'candidates', []), error=repr(error)), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
