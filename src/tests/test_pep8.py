"""
collect errors into the xunit report for CI integration.
"""
import os
import re

import pep8
from nose.tools import assert_true  # pylint: disable=E0611

PROJ_ROOT = "otto"
IGNORE = "E501,W291,W293,E261,E401,W391,E303,E202,E302,E201,W0511,C0112"


def fail(msg):
    """
    Fails with message.
    """
    assert_true(False, msg)


class CustomReport(pep8.StandardReport):
    """
    Collect report into an array of results.
    """
    results = []

    def get_file_results(self):
        if self._deferred_print:
            self._deferred_print.sort()
            for line_number, offset, code, text, _ in self._deferred_print:
                self.results.append({
                    'path': self.filename,
                    'row': self.line_offset + line_number,
                    'col': offset + 1,
                    'code': code,
                    'text': text,
                })
        return self.file_errors


def test_pep8():
    """
    Test for pep8 conformance
    """
    pattern = re.compile(r'({0}.*\.py)'.format(PROJ_ROOT))
    pep8style = pep8.StyleGuide(reporter=CustomReport)

    base = os.path.dirname(os.path.abspath(__file__))
    dirname = os.path.abspath(os.path.join(base, '..', PROJ_ROOT))

    sources = [
        os.path.join(root, pyfile) for root, _, files in os.walk(dirname)
        for pyfile in files
        if pyfile.endswith('.py')]

    report = pep8style.init_report()
    pep8style.options.ignore += tuple(IGNORE.split(','))
    pep8style.check_files(sources)

    for error in report.results:
        msg = 'File "{path}", line {row}, {col}\n\t {code} - {text}'
        match = pattern.match(error['path'])
        if match:
            rel_path = match.group(1)
        else:
            rel_path = error['path']

        yield fail, msg.format(
            path=rel_path,
            code=error['code'],
            row=error['row'],
            col=error['col'],
            text=error['text']
        )
