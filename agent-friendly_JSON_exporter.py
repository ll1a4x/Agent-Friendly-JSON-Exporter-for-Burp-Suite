# Burp Extension: Export proxy history as agent-friendly JSON
from burp import IBurpExtender, IContextMenuFactory
from javax.swing import JMenuItem, JFileChooser
from java.util import ArrayList
from datetime import datetime
import json
import re

class BurpExtender(IBurpExtender, IContextMenuFactory):
    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        callbacks.setExtensionName("Agent-Friendly JSON Exporter")
        callbacks.registerContextMenuFactory(self)

    def createMenuItems(self, invocation):
        menu = ArrayList()
        menu.add(JMenuItem("Export as JSON (full)",
            actionPerformed=lambda e: self.export(invocation, mode='full')))
        menu.add(JMenuItem("Export as JSONL (index)",
            actionPerformed=lambda e: self.export(invocation, mode='index')))
        menu.add(JMenuItem("Export both (index + full)",
            actionPerformed=lambda e: self.export(invocation, mode='both')))
        return menu

    def parse_headers(self, header_list):
        """Convert list of 'Key: Value' strings into a dict."""
        headers = {}
        for h in list(header_list)[1:]:  # skip first line (request/status line)
            if ':' in h:
                key, _, val = h.partition(':')
                headers[key.strip()] = val.strip()
        return headers

    def parse_query_params(self, url):
        """Extract query params into a dict."""
        params = {}
        if '?' in url:
            query = url.split('?', 1)[1]
            for pair in query.split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    params[k] = v
                else:
                    params[pair] = ''
        return params

    def detect_body_type(self, headers):
        """Identify content-type family for easier agent parsing."""
        ctype = headers.get('Content-Type', '').lower()
        if 'json' in ctype:
            return 'json'
        if 'xml' in ctype:
            return 'xml'
        if 'x-www-form-urlencoded' in ctype:
            return 'form'
        if 'multipart' in ctype:
            return 'multipart'
        if 'html' in ctype:
            return 'html'
        if 'javascript' in ctype or 'ecmascript' in ctype:
            return 'javascript'
        if any(b in ctype for b in ['image/', 'video/', 'audio/', 'octet-stream']):
            return 'binary'
        return 'text' if ctype else None

    def truncate_if_huge(self, body, body_type, max_len=50000):
        """Skip body content for binary or oversized responses."""
        if body_type == 'binary':
            return "<binary content omitted, length=%d>" % len(body)
        if len(body) > max_len:
            return body[:max_len] + ("\n<truncated, %d more bytes>" % (len(body) - max_len))
        return body

    def build_entry(self, msg, item_id):
        req_info = self._helpers.analyzeRequest(msg)
        req_bytes = msg.getRequest()
        req_body = self._helpers.bytesToString(req_bytes[req_info.getBodyOffset():])
        req_headers = self.parse_headers(req_info.getHeaders())
        url = str(req_info.getUrl())
        req_body_type = self.detect_body_type(req_headers)

        entry = {
            'id': item_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'url': url,
            'host': req_info.getUrl().getHost(),
            'port': req_info.getUrl().getPort(),
            'protocol': req_info.getUrl().getProtocol(),
            'method': req_info.getMethod(),
            'path': req_info.getUrl().getPath(),
            'query_params': self.parse_query_params(url),
            'request': {
                'headers': req_headers,
                'body': self.truncate_if_huge(req_body, req_body_type) if req_body else None,
                'body_type': req_body_type,
                'body_length': len(req_body),
            },
            'response': None,
        }

        resp_bytes = msg.getResponse()
        if resp_bytes:
            resp_info = self._helpers.analyzeResponse(resp_bytes)
            resp_body = self._helpers.bytesToString(resp_bytes[resp_info.getBodyOffset():])
            resp_headers = self.parse_headers(resp_info.getHeaders())
            resp_body_type = self.detect_body_type(resp_headers)
            entry['response'] = {
                'status': resp_info.getStatusCode(),
                'headers': resp_headers,
                'body': self.truncate_if_huge(resp_body, resp_body_type),
                'body_type': resp_body_type,
                'body_length': len(resp_body),
                'mime_type': resp_info.getStatedMimeType(),
            }

        return entry

    def build_index_entry(self, entry):
        """Compact one-line summary for JSONL index."""
        return {
            'id': entry['id'],
            'method': entry['method'],
            'url': entry['url'],
            'status': entry['response']['status'] if entry['response'] else None,
            'len': entry['response']['body_length'] if entry['response'] else 0,
            'ctype': entry['response']['body_type'] if entry['response'] else None,
        }

    def export(self, invocation, mode='full'):
        messages = invocation.getSelectedMessages()
        entries = [self.build_entry(m, i + 1) for i, m in enumerate(messages)]

        chooser = JFileChooser()
        chooser.setDialogTitle("Choose export directory")
        chooser.setFileSelectionMode(JFileChooser.DIRECTORIES_ONLY)
        if chooser.showSaveDialog(None) != JFileChooser.APPROVE_OPTION:
            return

        out_dir = chooser.getSelectedFile().getAbsolutePath()

        if mode in ('full', 'both'):
            full_path = out_dir + '/proxy_full.json'
            payload = {
                'metadata': {
                    'export_time': datetime.utcnow().isoformat() + 'Z',
                    'total_items': len(entries),
                },
                'items': entries,
            }
            with open(full_path, 'w') as f:
                json.dump(payload, f, indent=2)
            print("Wrote %d items to %s" % (len(entries), full_path))

        if mode in ('index', 'both'):
            index_path = out_dir + '/proxy_index.jsonl'
            with open(index_path, 'w') as f:
                for entry in entries:
                    f.write(json.dumps(self.build_index_entry(entry)) + '\n')
            print("Wrote index to %s" % index_path)
