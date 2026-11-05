"""Expose concise pytest diagnostics in GitHub annotations when raw logs are unavailable."""
import sys
from pathlib import Path
from xml.etree import ElementTree


def report(path):
    if not Path(path).is_file():
        print('::error::Pytest did not produce its JUnit report; inspect collection and dependencies.')
        return
    root = ElementTree.parse(path).getroot()
    for case in root.iter('testcase'):
        for tag in ('failure', 'error'):
            issue = case.find(tag)
            if issue is not None:
                message = case.get('classname', '') + '.' + case.get('name', '') + ': ' + (issue.get('message') or issue.text or '')
                message = message[:3000].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
                print('::error::' + message)


if __name__ == '__main__':
    report(sys.argv[1])
