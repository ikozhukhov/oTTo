import sys
from logging import getLogger, NullHandler
import logging

from otto.lib.log import COMMENT

logger = getLogger("otto")
if not logger.handlers:
    logger.addHandler(NullHandler())

logpath = "./"


def comment(msg, *args, **kws):
    # Yes, logger takes its '*args' as 'args'.
    logger._log(COMMENT, msg, args, **kws)


logger.comment = comment

fname = 'otto'

fmt = "%(asctime)s:%(filename)s->%(funcName)s:%(lineno)s %(message)s"

DebugFmt = logging.Formatter("%(asctime)s:%(filename)s->%(funcName)s:%(lineno)s %(message)s")
DebugLogHandler = logging.FileHandler(fname + ".debug")
DebugLogHandler.setLevel(logging.DEBUG)
DebugLogHandler.setFormatter(DebugFmt)

NormalFmt = logging.Formatter("%(asctime)s:%(filename)s->%(funcName)s:%(lineno)s %(message)s")
NormalLogHandler = logging.FileHandler(fname + ".log")
NormalLogHandler.setLevel(logging.INFO)
NormalLogHandler.setFormatter(NormalFmt)

StdOutFmt = logging.Formatter("%(asctime)s:%(filename)s->%(funcName)s:%(lineno)s %(message)s")
StdOutFmtHandler = logging.StreamHandler(sys.stdout)
StdOutFmtHandler.setLevel(logging.INFO)
StdOutFmtHandler.setFormatter(StdOutFmt)

logger.addHandler(DebugLogHandler)
logger.addHandler(NormalLogHandler)

logger.setLevel(logging.DEBUG)
