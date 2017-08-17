import os
import re
import html
import json
from collections import OrderedDict
import subprocess
import contextlib


def sanitize_url(url):
    if '://' not in url:
        return 'http://%s' % (url,)
    return url


def insert_string_to_html(op):
    text = html.escape(op['insert'])
    if 'attributes' in op:
        attr = op['attributes']
        if 'bold' in attr and attr['bold']:
            text = '<strong>%s</strong>' % text
        if 'italic' in attr and attr['italic']:
            text = '<em>%s</em>' % text
        if 'link' in attr:
            url = sanitize_url(attr['link'])
            text = '<a href="%s">%s</a>' % (html.escape(url, True), text)
    return text


def insert_image_to_html(op):
    return '<img src="%s" />' % (op['insert']['image'],)


def inline_delta_to_html(ops):
    parts = []
    for op in ops:
        if isinstance(op['insert'], str):
            part = insert_string_to_html(op)
        elif 'image' in op['insert']:
            part = insert_image_to_html(op)
        parts.append(part)
    return ''.join(parts)


def _close_tag(tag_stack):
    tag = tag_stack.pop().split(':')[0]
    whitespace = '  ' * len(tag_stack)
    yield '%s</%s>\n' % (whitespace, tag,)


def _close_tags(tag_stack, except_tag=None, except_css=None):
    if not except_tag:
        while tag_stack:
            yield from _close_tag(tag_stack)
    else:
        css_str = ''
        if except_css:
            css_str = ';'.join('%s:%s' % (k, v) for k, v in except_css.items())
        except_ = '%s:%s' % (except_tag, css_str)
        while tag_stack and tag_stack[-1] != except_:
            yield from _close_tag(tag_stack)


def _open_tag(tag_stack, tag, css={}):
    css_str = ''
    dom_attr = ''
    if css:
        css_str = ';'.join('%s:%s' % (k, v) for k, v in css.items())
        dom_attr = ' style="%s"' % (html.escape(css_str, True),)
    whitespace = '  ' * len(tag_stack)
    tag_stack.append('%s:%s' % (tag, css_str))
    yield '%s<%s%s>\n' % (whitespace, tag, dom_attr)


def _tag(tag_stack, tag, content, css=None):
    yield from _open_tag(tag_stack, tag, css)
    ws = '  ' * len(tag_stack)
    yield ws
    yield content.strip().replace('\n', '\n' + ws)
    yield '\n'
    yield from _close_tag(tag_stack)


def _process_block(tag_stack, ops, line_op=None):
    attr = []
    if line_op and 'attributes' in line_op:
        attr = line_op['attributes']
    css = OrderedDict()
    if 'align' in attr:
        assert attr['align'] in ('right', 'align', 'justify', 'center')
        css['text-align'] = attr['align']
    if 'header' in attr:
        yield from _close_tags(tag_stack)
        content = inline_delta_to_html(ops)
        assert '\n' not in content
        tag = 'h%d' % (attr['header'],)
        yield from _tag(tag_stack, tag, content, css)
    elif 'list' in attr:
        tag = 'ol' if attr['list'] == 'ordered' else 'ul'
        yield from _close_tags(tag_stack, tag)
        if not tag_stack:
            yield from _open_tag(tag_stack, tag)
        content = ''.join(_process_block([], ops))
        yield from _tag(tag_stack, 'li', content, css)
    else:
        yield from _close_tags(tag_stack, 'p')
        content = inline_delta_to_html(ops)
        parts = list(filter(None, re.split(r'\n+', content.strip())))
        if not parts:
            return
        for part in parts[:-1]:
            yield from _tag(tag_stack, 'p', part)
        yield from _tag(tag_stack, 'p', parts[-1], css)


def _process_single_entry_block(tag_stack, op):
    yield from _close_tags(tag_stack)


def _delta_to_html(delta):
    tag_stack = []
    ops = []
    for op in delta:
        if 'insert' not in op:
            yield from _process_block(tag_stack, ops)
            yield from _process_single_entry_block(tag_stack, op)
            ops = []
        elif op['insert'] == '\n':
            yield from _process_block(tag_stack, ops, op)
            ops = []
        elif '\n' in op['insert']:
            lines = op['insert'].split('\n')
            ops.append({
                'insert': lines[0]
            })
            yield from _process_block(tag_stack, ops)
            for line in filter(None, lines[1:-1]):
                ops = [{
                    'insert': line
                }]
                yield from _process_block(tag_stack, ops)
            new_op = op.copy()
            new_op['insert'] = lines[-1]
            ops = [new_op]
        else:
            ops.append(op)
    if ops:
        yield from _process_block(tag_stack, ops)
    yield from _close_tags(tag_stack)


def delta_to_html(delta):
    return ''.join(_delta_to_html(delta))


_process = None


@contextlib.contextmanager
def _html_to_delta_process():
    global _process
    if _process is None:
        here = os.path.dirname(os.path.realpath(__file__))
        file = os.path.join(here, 'html2quill.js')
        _process = subprocess.Popen(['nodejs', file],
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE)
    yield _process


def html_to_delta(html):
    if not html:
        # optimization: avoid invoking subprocess unnecessarily
        return {"ops": []}
    with _html_to_delta_process() as process:
        process.stdin.write(html.encode('UTF-8') + b'\0')
        process.stdin.flush()
        stdout = b''
        while b'\0' not in stdout:
            stdout += process.stdout.read1(2**20)
    return json.loads(str(stdout, 'UTF-8').split('\0', 1)[0])
