import argparse
import ast
import ConfigParser
import inspect
import os
import re
import sys

from otto.lib.otypes import Namespace
from  otto.initiators import linux
import otto.initiators.solaris as solaris


def parse_config():
    """
    parse the config file and return a Namespace object representing the configuration.  Values which can be
    interpreted by the ast module as numbers, tuples, lists, dicts, booleans, and None will become those types
    in the Namspace.  Otherwise they will be considered strings.
    """
    parser = argparse.ArgumentParser(conflict_handler='resolve')
    parser.add_argument('-c', '--config', metavar='<filename>', required=False, help='Path to the config file')
    arg_pattern = re.compile('^-|--')

    # Prep parse_args for potential command line arguments
    for arg in sys.argv:
        if arg == '-c' or arg == '--config':
            continue
        if arg_pattern.match(arg):
            parser.add_argument(arg)
    args = parser.parse_args()
    args_dict = vars(args)

    # Determine which file to use
    if args.config:
        path = args.config
        if not os.path.exists(path):
            raise Exception("File %s does not exist" % path)
    elif os.path.exists('./local.cfg'):
        path = './local.cfg'
    elif os.path.exists('/etc/otto/local.cfg'):
        path = '/etc/otto/local.cfg'
    else:
        raise Exception("No configuration supplied and no default configuration could be found.")

    # Parse config file to dictionary
    config = file_to_dict(path)

    # Overwrite/append command line config entries in config dictionary.
    for key in args_dict.keys():
        try:
            res = re.match('(\w+):(\w+)', key)
            try:
                config[res.group(1)][res.group(2)] = ast.literal_eval(args_dict[key])
            except:
                config[res.group(1)][res.group(2)] = args_dict[key]
        except AttributeError:
            pass

    return Namespace(config)


def init_steps(config, source=None):
    # Process steps                                                                                                                                               
    if config['General'].get('steps'):
        steps = []

        if source:
            calling_module = inspect.getmodulename(source)
        else:
            calling_frame = inspect.stack()[1]
            calling_file = calling_frame[1]
            calling_module = inspect.getmodulename(calling_file)

        mod = __import__(calling_module)

        # Steps need to be the exact function so that it can be executed.                                                                                         

        for step in config['General'].get('steps'):
            fun = getattr(mod, step)
            if inspect.isfunction(fun):
                steps.append(fun)
        config['General']['steps'] = steps

    return config


def file_to_dict(f):
    if os.path.exists(f):
        d = {}
        config_file = f
        cfg = ConfigParser.ConfigParser()
        cfg.read(config_file)
        sections = cfg.sections()

        for section in sections:
            section_items = {}
            items = cfg.items(section)
            for k, v in items:
                try:
                    section_items[k] = ast.literal_eval(v)
                except (SyntaxError, ValueError):
                    section_items[k] = v
            d[section] = section_items
    else:
        raise Exception("File %s does not exist" % f)

    return d


def compare(gold_file, subject_file):
    """
    Compare a config file against a gold file to verify the components
    of the config file are valid.
    
    The return result is True or False
    
    The function returns True if everything entry the config file matches
    the options of the gold file.
    
    The function returns false if there are missing, or unexpected components
    """

    subject_status = True
    gold_config = file_to_dict(gold_file)
    subject_config = file_to_dict(subject_file)

    print "Comparing %s against %s" % (subject_file, gold_file)

    missing_sections = list(set(gold_config.keys()) - set(subject_config.keys()))
    unknown_sections = list(set(subject_config.keys()) - set(gold_config.keys()))
    common_sections = list(set(gold_config.keys()) & set(subject_config.keys()))

    if missing_sections:
        print "Config file %s is missing the following section(s):" % subject_file
        for section_name in missing_sections:
            print "\t%s" % section_name

    if unknown_sections:
        subject_status = False
        print "Config file %s is contains the following unexpected section(s):" % subject_file
        for section_name in unknown_sections:
            print "\t%s" % section_name

    for section_name in common_sections:
        print "Verify values in section %s:" % section_name
        gold_section_data = gold_config[section_name]
        subject_section_data = subject_config[section_name]

        missing_section_data = list(set(gold_section_data.keys()) - set(subject_section_data.keys()))
        unknown_section_data = list(set(subject_section_data.keys()) - set(gold_section_data.keys()))

        if missing_section_data:
            print "\tConfig file %s is missing the following item(s) in section %s:" % (subject_file,
                                                                                        section_name)
            for missing_data in missing_section_data:
                print '\t\t%s' % missing_data

        if unknown_section_data:
            subject_status = False
            print "\tConfig file %s contains unexpected item(s) in section %s:" % (subject_file,
                                                                                   section_name)
            for unknown_data in unknown_section_data:
                print '\t\t%s' % unknown_data

        if not missing_section_data and not unknown_section_data:
            print "\tSection is okay!"

    return subject_status


def auto_config(cfg, kind):
    """
    This auto selects and returns an object from a config object. Currently can only
    return initiators, linux or solaris based on setting General.initos.

    :param cfg: a config object
    :type cfg: Namespace
    :param kind: what kind of thing to configure
    :type kind: str
    :return: an instanciation of the kind requested
    """
    initiators = {
        'linux': ('lnx_host_1', linux.LinuxSsh),
        'solaris': ('sol_host_1', solaris.SolarisSsh),
    }

    if kind is 'initiator':
        ostype = cfg.General.get('initos')

        if ostype:
            c = cfg.get(initiators[ostype][0])
            initclass = initiators[ostype][1]
        else:
            raise NotImplementedError("Autoselecting without 'initos' being set is not supported")
    else:
        raise NotImplementedError("Only initiators can be autoselected")

    return initclass(c)
