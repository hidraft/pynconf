#!/usr/bin/env python3
import settings
import sys, os
import generic
import yaml
import warnings
warnings.filterwarnings(action='ignore',module='.*paramiko.*')
from colorama import init, deinit, Fore, Style
import concurrent.futures


def get_configuration_from_router(data):

    # configuration from YAMLs

    router_vars = generic.get_router_varibles(data)
    data['system_hostname'] = router_vars['system']['hostname']

    # get configuration from all routers

    configuration_from_router = generic.get_config_from_router(data)
    old_config_file = generic.get_file_path(data['router_hostname'], 'current.cfg')
    with open(old_config_file, "w") as outfile:
        outfile.write(configuration_from_router)
        sys.stdout.write(Fore.CYAN + Style.BRIGHT +'\n{0} configuration saved\n'.format(data['router_hostname']))
        sys.stdout.flush()

def prepare_data():
    with open(settings.HOSTS_FILE, 'r') as stream:
        try:
            data = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(get_configuration_from_router, data['routers'])


if __name__ == "__main__":
    prepare_data()

