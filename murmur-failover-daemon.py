#!/usr/bin/env python
# -*- coding: utf-8
# Author: Oddbjørn Haaland
# Licensed under the MIT license
from os import sep, kill, path, makedirs
from sys import exit
from time import sleep, time
from struct import pack
from daemon import runner
from shutil import copyfile
from signal import SIGKILL, SIGTERM
from settings import data
from datetime import datetime
from subprocess import call
import logging, socket

class cfg():
    LOG_PATH = data['failover']['daemon']['logpath']
    ERR_PATH = data['failover']['daemon']['errpath']
    PID_PATH = data['failover']['daemon']['pidpath']

    SSH_PORT = str(int(data['main']['ssh']['port'])) # SSH port only used in sh
    SSH_USER = str(data['main']['ssh']['user'])
    SSH_HOST = data['main']['ssh']['host']

    MURMUR_HOST = data['main']['murmur']['host']
    MURMUR_PORT = int(data['main']['murmur']['port'])
    MURMUR_DB = data['main']['murmur']['dbfile']
    MURMUR_EXE = data['main']['murmur']['executable']
    MURMUR_PID = data['main']['murmur']['pidfile']
    MURMUR_CFG = data['main']['murmur']['cfgfile']

    # Force single folder path seperator at end of paths
    MURMUR_PATH = data['main']['murmur']['path'].rstrip(sep) + sep
    FAILOVER_MURMUR_PATH = data['failover']['murmur']['path'].rstrip(sep) + sep

    # Controls how often the daemon runs code (decides sleep duration)
    PING_INTERVAL = int(data['failover']['interval']['ping'])

    # A sync can only occur at the same time as a ping
    SYNC_INTERVAL = int(data['failover']['interval']['sync'])

    # A pingCount is incremented every time a ping is done, when the counter
    # reaches PING_COUNT_MAX, the pingCount will reset, and a sync is done
    PING_COUNT_MAX = int(SYNC_INTERVAL / PING_INTERVAL)

    # For this reason, the sync interval can not be less than the ping interval
    if SYNC_INTERVAL < PING_INTERVAL:
        SYNC_INTERVAL = PING_INTERVAL


class MurmurFailover():
    def __init__(self):
        if not path.exists(path.dirname(cfg.ERR_PATH)):
            makedirs(path.dirname(cfg.ERR_PATH))
        if not path.exists(path.dirname(cfg.PID_PATH)):
            makedirs(path.dirname(cfg.PID_PATH))

        self.stdin_path = "/dev/null"
        self.stdout_path = "/dev/null"
        self.stderr_path = cfg.ERR_PATH
        self.pidfile_path = cfg.PID_PATH
        self.pidfile_timeout = 5


    # Daemon - Poll main Murmur and sync DB
    def run(self):
        self.do_initial_sync()

        upNow = True
        pingCount = cfg.PING_COUNT_MAX

        # Start the infinite daemon loopage!
        while True:
            upLastTime = upNow
            upNow = self.poll_murmur(cfg.MURMUR_HOST, cfg.MURMUR_PORT)
            if not upNow:
                sleep(1)
                upNow = self.poll_murmur(cfg.MURMUR_HOST, cfg.MURMUR_PORT)

            # pingCount exceed PING_COUNT_MAX only if server down when we sync
            if upNow and pingCount >= cfg.PING_COUNT_MAX:
                pingCount = 0
                self.sync_db_and_config()

            # ?: Main Murmur has gone from being down, to being up
            if upNow and not upLastTime:
                # -> Kill local Murmur failover process
                LOG.info("Main Murmur is back up again, killing local failover"
                        " Murmur process")
                try:
                    with open(cfg.FAILOVER_MURMUR_PATH + cfg.MURMUR_PID) as f:
                        pid = int(f.readline())
                except IOError as e:
                    LOG.error("Couldn't open PID file for reading when"
                            " attempting to kill local Murmur process. Did you"
                            " remember to set a pidfile in the main Murmur"
                            " server's config? Exiting.")
                    exit(1)

                kill(pid, SIGTERM)
                sleep(1)

                # Make sure we managed to kill the process, send a SIGKILL
                try:
                    kill(pid, SIGKILL)
                    # Check if the process is still there, OSError if not
                    kill(pid, 0)

                    # We were unable to kill it, exit the process
                    LOG.error("Unable to kill failover Murmur process, exiting")
                    exit(1)
                except OSError as e:
                    pass

            # ?: Main Murmur has gone from being up, to being down
            elif upLastTime and not upNow:
                # -> Copy (and replace) .sqlite.bak DB to .sqlite
                dst = cfg.FAILOVER_MURMUR_PATH + cfg.MURMUR_DB
                src = dst + ".bak"
                try:
                    copyfile(src, dst)
                except IOError as e:
                    LOG.error("An error occured while preparing the database"
                            " before starting failover Murmur (no DB found?)")
                    exit(1)
                # Start Backup Murmur Server
                LOG.info("Main Murmur went down, starting failover Murmur")
                murmurExitCode = call(
                        [cfg.FAILOVER_MURMUR_PATH + cfg.MURMUR_EXE, "-v"])
                if murmurExitCode > 0:
                    LOG.error("An error occured while trying to start the"
                            " failover Murmur, exiting. (exit code: {0})"
                            .format(murmurExitCode))
                    exit(1)

            pingCount += 1
            sleep(cfg.PING_INTERVAL)


    # Look for Murmur executable locally, and rsync everything except logs
    # and the DB from main Murmur server if it doesn't already exist
    def do_initial_sync(self):
        try:
            with open(cfg.FAILOVER_MURMUR_PATH + cfg.MURMUR_EXE) as f: pass
        except IOError as e:
            # Initial Murmur rsync from main Murmur server
            # in case certain files do not exist locally
            LOG.warning("No local Murmur files detected, copying from main"
                    " Murmur server (performing initial sync)")
            rsyncExitCode = call(["rsync",
                    "--archive", # recursive
                    "--verbose",
                    "--compress",
                    "--exclude", cfg.MURMUR_DB,
                    "--exclude", "*.log",
                    # -e allows us to set a non-default SSH port
                    "-e", "ssh -p {0}".format(cfg.SSH_PORT),
                    # get files from here (main Murmur server)
                    "{0}@{1}:'{2}'"
                    .format(cfg.SSH_USER, cfg.SSH_HOST, cfg.MURMUR_PATH),
                    # put files in here (failover Murmur server)
                    cfg.FAILOVER_MURMUR_PATH
            ])
            if rsyncExitCode > 0:
                LOG.error("Something went wrong during initial Murmur rsync,"
                        " exit code {0}".format(rsyncExitCode))
                exit(1)

            # Error out if the file still isn't there
            try:
                with open(cfg.FAILOVER_MURMUR_PATH + cfg.MURMUR_EXE) as f: pass
            except IOError as e:
                LOG.error("Couldn't copy Murmur executable from main Murmur"
                        " server, exiting.")
                exit(1)
            LOG.debug("Initial sync completed successfully")


    def poll_murmur(self, host, port):
        # Based on pcgod's mumble-ping script at http://0xy.org/mumble-ping.py
        ping = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ping.settimeout(2)
        # Prepare a special ping packet and send to Murmur server
        packet = pack(">iQ", 0, datetime.now().microsecond)
        ping.sendto(packet, (host, port))
        # Expect a response
        try:
            ping.recvfrom(1024)
        except socket.timeout:
            # Murmur is down, no response before timeout
            ping.close()
            return False
        # Murmur is up
        ping.close()
        return True


    def sync_db_and_config(self):
        LOG.debug("Syncing DB and config")
        # Perform sqlite3 DB backup remotely via SSH
        shellCall = ["ssh",
                "-p", cfg.SSH_PORT,
                "{0}@{1}".format(cfg.SSH_USER, cfg.SSH_HOST),
                "sqlite3 '{0}{1}' '.backup \"{0}{1}.bak\"'"
                .format(cfg.MURMUR_PATH, cfg.MURMUR_DB)
        ]
        sshExitCode = call(shellCall)
        if sshExitCode > 0:
            LOG.warning("Something went wrong during sqlite backup of Murmur DB"
                    " (via SSH), exit code {0}. Trying again in 1 second."
                    .format(sshExitCode))
            sleep(1)
            sshExitCode = call(shellCall)
            if sshExitCode > 0:
                LOG.error("Something went wrong (twice!) during sqlite backup"
                        " of Murmur DB (via SSH), exit code {0}. DB sync not"
                        " successful".format(sshExitCode))
                return False

        # Rsync config + the previously created sqlite backup file
        rsyncExitCode = call(["rsync",
                "--archive", # recursive
                "--compress",
                "--include", "{0}.bak".format(cfg.MURMUR_DB),
                "--include", cfg.MURMUR_CFG,
                "--exclude", "*", # only rsync selected files
                # -e allows us to set a non-default SSH port
                "-e", "ssh -p {0}".format(cfg.SSH_PORT),
                # get files from here (main Murmur server)
                "{0}@{1}:'{2}'"
                .format(cfg.SSH_USER, cfg.SSH_HOST, cfg.MURMUR_PATH),
                # put files in here (failover Murmur server)
                cfg.FAILOVER_MURMUR_PATH
        ])
        if rsyncExitCode > 0:
            LOG.error("Something went wrong during DB/config rsync, exit code"
                    " {0}. DB sync not successful".format(rsyncExitCode))
            return False
        LOG.debug("DB sync completed successfully")
        return True


# Prepare logging
if not path.exists(path.dirname(cfg.LOG_PATH)):
    makedirs(path.dirname(cfg.LOG_PATH))
try:
    with open(cfg.LOG_PATH, 'w') as f: pass
except IOError as e:
    print "Can't write to log file, exiting."
    exit(1)
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)
formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.FileHandler(cfg.LOG_PATH)
handler.setFormatter(formatter)
LOG.addHandler(handler)

# Prepare for daemonization
murmurFailover = MurmurFailover()
daemon_runner = runner.DaemonRunner(murmurFailover)

# Ensure that the logging file handler does not get closed during daemonization
daemon_runner.daemon_context.files_preserve=[handler.stream]

# Go into daemon mode
daemon_runner.do_action()
