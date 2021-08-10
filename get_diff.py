#!/usr/bin/env python3
import settings
import generic
import yaml
import sys, os
import warnings
warnings.filterwarnings(action='ignore',module='.*paramiko.*')
import sys
from colorama import init, deinit, Fore, Style

init(autoreset=True)

import signal
import sys

def signal_handler(sig, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def compare(data):


    # configuration from YAMLs

    router_vars = generic.get_router_varibles(data)
    data['system_hostname'] = router_vars['system']['hostname']

    ## render template

    config = generic.render_jinja_template(data, router_vars)
    config_file = generic.get_file_path(data['router_hostname'], 'rendered.cfg')
    with open(config_file, "w") as outfile:
        outfile.write(config)

    # check what has been updated
    changet_files = generic.get_changet_files()
    if generic.if_router_in_changet_files(data, changet_files):

        # compare configurations
        diff = generic.get_diff_from_router(data, config_file)
        sys.stdout.write(Fore.CYAN + Style.BRIGHT + "\n##########"+len(data['router_hostname'])*"#"+"################\n")
        sys.stdout.write(Fore.CYAN + Style.BRIGHT + "| Compare {0} configuration |".format(data['router_hostname']))
        sys.stdout.write(Fore.CYAN + Style.BRIGHT + "\n##########"+len(data['router_hostname'])*"#"+"################\n")
        if diff:
            sys.stdout.flush()
            sys.stdout.write(diff)
            sys.stdout.flush()
        else:
            sys.stdout.write('SAME\n')
            sys.stdout.flush()
        sys.stdout.write(Fore.CYAN + Style.BRIGHT + "\n##########"+len(data['router_hostname'])*"#"+"###\n")
        sys.stdout.write(Fore.CYAN + Style.BRIGHT + "| Done for {0} |".format(data['router_hostname']))
        sys.stdout.write(Fore.CYAN + Style.BRIGHT + "\n##########"+len(data['router_hostname'])*"#"+"###\n")
    '''
    '''

def prepare_data():
    with open(settings.HOSTS_FILE, 'r') as stream:
        try:
            data = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
    for router_data in data['routers']:
        compare(router_data)

if __name__ == "__main__":
    sys.stdout.write(Fore.CYAN + Style.BRIGHT + " START \n")
    sys.stdout.flush()
    prepare_data()
    sys.stdout.write(Fore.CYAN + Style.BRIGHT + " STOP \n")
    sys.stdout.flush()

