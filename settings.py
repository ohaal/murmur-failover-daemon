# Wrap all config values (except numbers) in quotes and end with a comma
data = {
    'main': {
        'murmur': {
            'path': "/home/murmur/murmur", # Absolute path
            'dbfile': "murmur.sqlite",      # Relative path
            'cfgfile': "murmur.ini",        # Relative path
            'pidfile': "murmur.pid",        # Relative path
            'executable': "murmur.x86",     # Relative path
            'host': "",    # Do NOT use the hostname configured with multi IP's!
            'port': 64738, # Default: 64738
        },
        'ssh': {
            'user': "murmur",
            'host': "", # Typically the same as main Murmur host
            'port': 22, # Default: 22
        }
    },
    'failover': { # USE ABSOLUTE PATHS
        'murmur': {
            'path': "/home/murmur/murmur"
        },
        'daemon': { # USE ABSOLUTE PATHS -- Don't put murmur-failover in Murmur
            'pidpath': "/home/murmur/murmur-failover/murmur-failover.pid",
            'logpath': "/home/murmur/murmur-failover/murmur-failover.log",
            'errpath': "/home/murmur/murmur-failover/stderr.log"
        },
        'interval': { # VALUES ARE IN SECONDS
            'ping': 3, # How often to check if main Murmur is alive
            'sync': 600, # How often to sync DB and CFG files
        }
    }
}