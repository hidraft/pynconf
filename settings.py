import os
import environ

ROOT_DIR = environ.Path()
HOME_DIR = os.environ['HOME']
TEMPLATES_ENVIRONMENT = os.path.join(ROOT_DIR, '')
CONFIG_FILES_DIRECTORY = ROOT_DIR.path('conf')
HOSTS_FILE = 'hosts.yaml'
SSH_CONFIG = '~/.ssh/config'
LOGLEVEL = 'DEBUG'
LIST_MERGE_KEY = 'merged_list'
HUAWEI_REGEX_RUNNING_SEARCH = '(?<=#\r\n).*return'
CISCO_REGEX_RUNNING_SEARCH = 'hostname.*end'
JUNIPER_REGEX_RUNNING_SEARCH = '(?<=;\r\n)system.*}'
EXPECT_LIST_ERRORS = ['Error.+',
        '% Invalid.+',
        '.+^.+',
        '% Incomplete.+',
        '% Unknown.+',
        'bad command.+',
        'failure.+',
        ]
CFG_FILR_NAME = 'gitlab.cfg'
HUAWEI_REMOTE_FILE_PATCH = CFG_FILR_NAME
CISCO_REMOTE_FILE_PATCH = 'disk0:/' + CFG_FILR_NAME
JUNIPER_REMOTE_FILE_PATCH = CFG_FILR_NAME

HUAWEI_GET_RUN =['screen-length 0 temporary',
                'display current-configuration',
                    ]
CISCO_GET_RUN = ['terminal length 0',
                'sh run',
                    ]
JUNIPER_GET_RUN = ['set cli screen-length 0',
                'show configuration',
                    ]

HUAWEI_GET_DIFF = ['screen-length 0 temporary',
                'sys',
                'load configuration file {} replace'.format(HUAWEI_REMOTE_FILE_PATCH),
                'display configuration candidate merge',
                    ]
CISCO_GET_DIFF = ['terminal length 0',
                'conf t',
                'load {}'.format(CISCO_REMOTE_FILE_PATCH),
                'show configuration',
                    ]
JUNIPER_GET_DIFF = ['set cli screen-length 0',
                'config',
                'load override {}'.format(JUNIPER_REMOTE_FILE_PATCH),
                'commit',
                'exit',
                    ]

HUAWEI_PUSH_CONFIG = ['screen-length 0 temporary',
                'sys',
                'load configuration file {} replace'.format(HUAWEI_REMOTE_FILE_PATCH),
                'display configuration replace failed',
                'commit',
                'run save',
                'y',
                    ]
CISCO_PUSH_CONFIG = ['terminal length 0',
                'conf t',
                'load {}'.format(CISCO_REMOTE_FILE_PATCH),
                'commit replace comment make by pnba',
                'y',
                    ]
JUNIPER_PUSH_CONFIG = ['set cli screen-length 0',
                'config',
                'load override {}'.format(JUNIPER_REMOTE_FILE_PATCH),
                'commit',
                'exit',
                    ]
