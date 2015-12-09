#!/usr/bin/env python
# encoding: utf-8
"""
Classes supporting logging from scripts and the executor.
"""
import datetime
import re
import logging
import sys
import inspect
import os
import itertools
import mimetools
import mimetypes
import urllib2
import string
import time
from logging import DEBUG, INFO, WARNING, ERROR
from logging.handlers import WatchedFileHandler

from otto.lib.otypes import ReturnCode

logging.COMMENT = 15
COMMENT = logging.COMMENT


class MultiPartForm(object):
    """Accumulate the data to be used when posting a form."""

    def __init__(self):
        self.form_fields = []
        self.files = []
        self.boundary = mimetools.choose_boundary()
        return

    def get_content_type(self):
        return 'multipart/form-data; boundary=%s' % self.boundary

    def add_field(self, name, value):
        """Add a simple field to the form data."""
        self.form_fields.append((name, value))
        return

    def add_file(self, fieldname, filename, fileHandle, mimetype=None):
        """Add a file to be uploaded."""
        body = fileHandle.read()
        if mimetype is None:
            mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        self.files.append((fieldname, filename, mimetype, body))
        return

    def __str__(self):
        """Return a string representing the form data, including attached files."""
        # Build a list of lists, each containing "lines" of the
        # request.  Each part is separated by a boundary string.
        # Once the list is built, return a string where each
        # line is separated by '\r\n'.  
        parts = []
        part_boundary = '--' + self.boundary

        # Add the form fields
        parts.extend(
            [part_boundary,
             'Content-Disposition: form-data; name="%s"' % name,
             '',
             value,
             ]
            for name, value in self.form_fields
        )

        # Add the files to upload
        parts.extend(
            [part_boundary,
             'Content-Disposition: file; name="%s"; filename="%s"' %
             (field_name, filename),
             'Content-Type: %s' % content_type,
             '',
             body,
             ]
            for field_name, filename, content_type, body in self.files
        )

        # Flatten the list and add closing boundary marker,
        # then return CR+LF separated data
        flattened = list(itertools.chain(*parts))
        flattened.append('--' + self.boundary + '--')
        flattened.append('')
        return '\r\n'.join(flattened)


class Dispatcher(logging.Formatter):
    instance = os.environ.get('instance') or ''
    defFormat = '%(levelname)-8s- %(asctime)-24s- %(filename)s->%(funcName)s:%(lineno)s - %(message)s'
    debugFormat = commentFormat = infoFormat = warningFormat = errorFormat = defFormat
    sources = {'otto' + instance + '.appliances', 'otto' + instance + '.connections', 'otto' + instance + '.initiators',
               'otto' + instance + '.lib', 'otto' + instance + '.gui', 'otto' + instance + '.utils'}

    def __init__(self):
        logging.Formatter.__init__(self, Dispatcher.defFormat)
        instance = os.environ.get('instance') or ''
        Dispatcher.sources = {'otto' + instance + '.appliances', 'otto' + instance + '.connections',
                              'otto' + instance + '.initiators', 'otto' + instance + '.lib', 'otto' + instance + '.gui',
                              'otto' + instance + '.utils'}

    def format(self, record):
        fmt = self._fmt

        if record.levelno == DEBUG:
            self._fmt = Dispatcher.debugFormat
        elif record.levelno == COMMENT:
            self._fmt = Dispatcher.commentFormat
        elif record.levelno == INFO:
            self._fmt = Dispatcher.infoFormat
        elif record.levelno == WARNING:
            self._fmt = Dispatcher.warningFormat
        elif record.levelno == ERROR:
            self._fmt = Dispatcher.errorFormat

        if record.name not in Dispatcher.sources:
            # Source for log record is UNKNOWN and preformatted according to the level determined by Dispatcher
            self._fmt = '%(message)s'

        result = logging.Formatter.format(self, record)

        # Reset the format
        self._fmt = fmt

        return result


class LogFilter:
    def __init__(self, level):
        self.__level = level

    def filter(self, record):
        return record.levelno == self.__level


def formatMesg(message, levelno, frame, fmt):
    """
    This function formats a log message according to the values of a log entry for programs
    making a call into the log class which bypass the dispatcher

    The possible configurable values for log format are::


        asctime = ''
        created = ''
        filename = ''
        funcName = ''
        levelname = ''
        levelno = ''
        lineno = ''
        module = ''
        msecs = ''
        message = ''
        name = ''
        pathname = ''
        process = ''
        processName = ''
        relativeCreated = ''
        thread = ''
        threadName = ''

    """

    info = inspect.getframeinfo(frame[0])

    asctime = datetime.datetime.now().strftime('%F %H:%M:%S,%f')[:-3]
    created = time.time()
    filename = os.path.basename(info.filename) or ''
    funcName = info.function or ''
    levelname = logging.getLevelName(levelno)
    lineno = info.lineno
    module = ''  # not implemented
    msec = datetime.datetime.now().strftime('%f')[:-3]
    name = ''  # not implemented
    pathname = info.filename
    process = ''  # not implemented
    processName = ''  # not implemented
    relativeCreated = ''  # not implemented
    thread = ''  # not implemented
    threadName = ''  # not implemented

    return fmt % {'asctime': asctime, 'created': created, 'filename': filename, 'funcName': funcName,
                  'levelname': levelname, 'levelno': levelno, 'lineno': lineno, 'message': message,
                  'module': module, 'msec': msec, 'name': name, 'pathname': pathname, 'process': process,
                  'processName': processName, 'relativeCreated': relativeCreated, 'thread': thread,
                  'threadName': threadName}


def setFormat(lvl, fmt):
    """
    Set the format for a specific log level.
    """
    if lvl == DEBUG:
        Dispatcher.debugFormat = fmt
    elif lvl == COMMENT:
        Dispatcher.commentFormat = fmt
    elif lvl == INFO:
        Dispatcher.infoFormat = fmt
    elif lvl == WARNING:
        Dispatcher.warningFormat = fmt
    elif lvl == ERROR:
        Dispatcher.errorFormat = fmt


class Log(object):
    def __init__(self, level=logging.DEBUG, name=None, logdir='./', stdout=True, multiFile=False, post=False,
                 ws='www-qa.coraid.com'):
        self.logdir = logdir
        self.ws = ws
        self.instance = os.environ.get('instance') or ''
        self.level = level
        logging.addLevelName(COMMENT, "COMMENT")

        # Root Logger
        self.logger = logging.getLogger('otto' + self.instance)
        self.logger.addHandler(logging.NullHandler())

        """
        Root Logger Threshold is WARNING by default.
        We will set the threshold as low as possible
        """
        self.logger.setLevel(DEBUG)

        """
        The STDOUT handler will use the logger default threshold for printing.
        If the level is set to INFO the STDOUT should only display INFO messages and greater
        """
        if stdout:
            StdOutHandler = logging.StreamHandler(sys.stdout)
            StdOutHandler._name = "STDOUT"
            StdOutHandler.setLevel(level)
            StdOutHandler.setFormatter(Dispatcher())
            self.logger.addHandler(StdOutHandler)

        if name is None:
            frame = inspect.stack()[1]
            name = inspect.getfile(frame[0]).split('/')[-1].split(".py")[0]

        logFileBase = self.logdir + name + "-" + time.strftime('%Y%m%d_%H%M')

        """
        The Full log will contain every level of output and will be created
        in any configuration for use when posting the log to the web server.
        """
        fullLogFile = logFileBase + "_FULL.log"
        self.fullLogFile = fullLogFile
        FullLogFileHandler = WatchedFileHandler(fullLogFile)
        FullLogFileHandler.setLevel(level)
        FullLogFileHandler._name = "LogFile-FULL"
        FullLogFileHandler.setFormatter(Dispatcher())
        self.logger.addHandler(FullLogFileHandler)

        """
        In the case of multiFile = True:
        Create a FileHandler for each level and attatch the appropriate level name to the file suffix
        Then set a filter on each handler to return only the appropriate level per file
        """
        if multiFile:
            # Set up filename variables
            debugLogFile = logFileBase + "_DEBUG.log"
            commentLogFile = logFileBase + "_COMMENT.log"
            infoLogFile = logFileBase + "_INFO.log"
            warningLogFile = logFileBase + "_WARNING.log"
            errorLogFile = logFileBase + "_ERROR.log"

            # Create FileHandler objects
            DebugFileHandler = WatchedFileHandler(debugLogFile)
            DebugFileHandler._name = "LogFile-DEBUG"
            CommentFileHandler = WatchedFileHandler(commentLogFile)
            CommentFileHandler._name = "LogFile-COMMENT"
            InfoFileHandler = WatchedFileHandler(infoLogFile)
            InfoFileHandler._name = "LogFile-INFO"
            WarningFileHandler = WatchedFileHandler(warningLogFile)
            WarningFileHandler._name = "LogFile-WARNING"
            ErrorFileHandler = WatchedFileHandler(errorLogFile)
            ErrorFileHandler._name = "LogFile-ERROR"

            # Add filters at corresponding levels
            DebugFileHandler.addFilter(LogFilter(DEBUG))
            CommentFileHandler.addFilter(LogFilter(COMMENT))
            InfoFileHandler.addFilter(LogFilter(INFO))
            WarningFileHandler.addFilter(LogFilter(WARNING))
            ErrorFileHandler.addFilter(LogFilter(ERROR))

            # Add format Dispatcher
            DebugFileHandler.setFormatter(Dispatcher())
            CommentFileHandler.setFormatter(Dispatcher())
            InfoFileHandler.setFormatter(Dispatcher())
            WarningFileHandler.setFormatter(Dispatcher())
            ErrorFileHandler.setFormatter(Dispatcher())

            # Add handlers to root logger
            self.logger.addHandler(DebugFileHandler)
            self.logger.addHandler(CommentFileHandler)
            self.logger.addHandler(InfoFileHandler)
            self.logger.addHandler(WarningFileHandler)
            self.logger.addHandler(ErrorFileHandler)

    def debug(self, msg):
        frame = inspect.stack()[1]
        msg = formatMesg(msg, DEBUG, frame, Dispatcher.debugFormat)
        self.logger.debug(msg)

    def comment(self, msg):
        frame = inspect.stack()[1]
        msg = formatMesg(msg, COMMENT, frame, Dispatcher.commentFormat)
        self.logger.log(COMMENT, msg)

    def info(self, msg):
        frame = inspect.stack()[1]
        msg = formatMesg(msg, INFO, frame, Dispatcher.infoFormat)
        self.logger.info(msg)

    def warning(self, msg):
        frame = inspect.stack()[1]
        msg = formatMesg(msg, WARNING, frame, Dispatcher.warningFormat)
        self.logger.warning(msg)

    def error(self, msg):
        frame = inspect.stack()[1]
        msg = formatMesg(msg, ERROR, frame, Dispatcher.errorFormat)
        self.logger.error(msg)

    def write(self, msg):
        """
        Put a message into the log.  This method can take a string or a result type dict.
        """
        frame = inspect.stack()[1]

        if type(msg) == str:
            msg = formatMesg(msg, COMMENT, frame, Dispatcher.commentFormat)
            self.logger.log(COMMENT, msg)
        elif type(msg) == dict:
            status = msg['status']
            if status == 'pass':
                msg['value'] = formatMesg(msg['value'], INFO, frame, Dispatcher.infoFormat)
                self.logger.info(msg['value'])
            elif status == 'warning':
                msg['value'] = formatMesg(msg['value'], WARNING, frame, Dispatcher.warningFormat)
                self.logger.warning(msg['value'])
            elif status == 'fail':
                msg['value'] = formatMesg(msg['value'], ERROR, frame, Dispatcher.errorFormat)
                self.logger.error(msg['value'])
            else:
                msg['value'] = formatMesg(msg['value'] + "Status: UNKNOWN", ERROR, frame, Dispatcher.errorFormat)
                self.logger.warning(msg['value'])
        elif type(msg) == ReturnCode:
            if msg:
                msg = formatMesg(str(msg), INFO, frame, Dispatcher.infoFormat)
                self.logger.info(msg)
            elif not msg:
                msg = formatMesg(str(msg), ERROR, frame, Dispatcher.errorFormat)
                self.logger.error(msg)
        else:
            print str(type(msg))

    def post(self):
        """
        Post data to self.ws through the post.py form
        """
        postUrl = 'http://' + self.ws + ':80/cgi-bin/post.py'

        # Create the form with simple fields
        logform = MultiPartForm()
        logfilename = string.rsplit(self.fullLogFile, '/', 1)[1]
        logform.add_file('file', logfilename, open(self.fullLogFile))
        body = str(logform)

        # Build the request
        request = urllib2.Request(postUrl)
        request.add_header('Content-type', logform.get_content_type())
        request.add_header('Content-length', len(body))
        request.add_data(body)

        # print request.get_data()
        urllib2.urlopen(request).read()

        htmlFile = self.format_html()
        htmlform = MultiPartForm()
        htmlfilename = string.rsplit(htmlFile, '/', 1)[1]
        htmlform.add_file('file', htmlfilename, open(htmlFile))

        request = urllib2.Request(postUrl)
        body = str(htmlform)
        request.add_header('Content-type', htmlform.get_content_type())
        request.add_header('Content-length', len(body))
        request.add_data(body)
        # request.get_data()
        response = urllib2.urlopen(request)
        data = response.read()

        s = re.search("^file location: (.+)", data, re.MULTILINE)
        location = s.group(1)

        print "http://%s%s\n" % (self.ws, location)

    def format_html(self):
        html = []

        errors = []
        error_count = 0

        warnings = []
        warning_count = 0

        log = open(self.fullLogFile)
        htmlFileName = re.sub('.log$', '.html', self.fullLogFile)

        for line in log:
            if re.search('ERROR', line):
                error_count += 1
                err = 'err' + str(error_count)
                errors.append('<a href="#err' + str(error_count) + '">' + str(error_count) + '</a>')
                html.append(
                    '<a name=' + err + ' />' + '<FONT COLOR="#FF0000">' + line + '</FONT><a href="#top">Back to top</a>\n')
            elif re.search('WARNING', line):
                warning_count += 1
                wrn = 'wrn' + str(warning_count)
                warnings.append('<a href="#wrn' + str(warning_count) + '">' + str(warning_count) + '</a>')
                html.append(
                    '<a name=' + wrn + ' />' + '<FONT COLOR="#FF9933">' + line + '</FONT><a href="#top">Back to top</a>\n')
            else:
                html.append(line)

        htmlFile = open(htmlFileName, 'w')
        htmlFile.write('<HTML>\n')

        htmlFile.write('<a name="top"/>')

        if not errors:
            htmlFile.write('Errors: 0\n')
        else:
            htmlFile.write('Errors: ' + ', '.join(errors) + '\n')

        htmlFile.write('<p/>\n')

        if not warnings:
            htmlFile.write('Warnings: 0\n')
        else:
            htmlFile.write('Warnings: ' + ', '.join(warnings) + '\n')

        htmlFile.write('<p/>\n')
        htmlFile.write('<br/>'.join(html))
        htmlFile.write('</HTML>\n')

        return htmlFileName

    def setLevel(self, level):
        """
        Changes the log level of existing log handlers
        """
        handlers = self.logger.handlers
        for handler in handlers:
            handler.setLevel(level)

    def logResult(self, tcid, result):
        """
        Write the log record to all log handlers
        TEST COMPLETED test ID: <test_id> status: <status>
        """
        record = logging.LogRecord(None, None, None, None, "TEST COMPLETED - ID: %s w/ STATUS: %s", (tcid, result),
                                   None)
        handlers = self.logger.handlers
        for handler in handlers:
            handler.emit(record)

    @property
    def fileHandlers(self):
        """
        Returns a list of active fileHandlers
        """
        fileHandlers = list()
        handlers = self.logger.handlers
        for handler in handlers:
            try:
                if handler._name.startswith("LogFile-"):
                    fileHandlers.append(handler)
            except:
                pass
        return fileHandlers

    @fileHandlers.setter
    def fileHandlers(self, handlers):
        """
        Appends additional fileHandlers to the log object
        """
        for handler in handlers:
            self.logger.addHandler(handler)
