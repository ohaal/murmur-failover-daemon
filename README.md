murmur-failover-daemon
======================

A simple hack utilizing DNS for automatic failover when a Murmur server dies, 
enabling simple and high availability Murmur server hosting with the use of two
servers.


## How does it work?
On most OSs, the Mumble client seems to do a round-robin connection attempt to
each of the IP addresses in the hostname's A record. If the connection attempt
fails, the next server in the list is attempted.

murmur-failover-daemon works by periodically syncing the database of the master
over to the slave. Meanwhile constantly pinging the master to see if it is up.
If the master goes down, the slave is started, and will begin accepting
connections. Mumble applications which are disconnected from the server will
naturally try to reconnect to the hostname it was previously connected, and in
doing so, be directed to the slave, because the master is no longer responding.
The slave continues to ping the master. When the master is back up, the slave
kills itself and clients will be redirected back to the master.

Any configuration or database changes made on the slave while the master is
down will be lost.


## Requirements
- A server running Murmur (on a static IP)
- Another server with the same ports open as the first one, different static IP
- A single hostname configured to point to the two IP addresses of the servers.
A typical zone file could look like this:

```
mumble.example.com.    3600 IN  A   127.0.0.1
mumble.example.com.    3600 IN  A   192.168.1.1
```

### Master Murmur host
- An open UDP port for Murmur (used for pings, checking if Murmur is up)
- A PID file set in the Murmur config file (will carry over to failover config)
- sqlite3

### Slave Murmur host
- rsync
- python-daemon
- SSH key with password-less access to master Murmur host
- This script


## Installation (for Debian based OS)

### Master Murmur host
1. Make sure both UDP and TCP port is open for Murmur
2. Set a PID file in the murmur.ini file
3. If sqlite3 is not installed, run `apt-get install sqlite3`
4. Create a password-less SSH key (needed in step 3 below)

### Slave Murmur host
1. If rsync is not installed, run `apt-get install rsync`
2. If python-daemon is not installed, run `apt-get install python-daemon`
3. Install the password-less SSH key you generated in step 4 above
4. Run `git clone https://github.com/ohaal/murmur-failover-daemon.git`
5. Make the script executable by running `chmod +x murmur-failover-daemon.py`
6. Edit the `settings.py` file

### (Optional) Installing the daemon as a service
Put the below example data in a new file (`/etc/init.d/murmur-failover.sh`),
editing the usernames and folder paths in the process.

```sh
### BEGIN INIT INFO
# Provides: Murmur Failover Daemon Control
# Required-Start: $local_fs $network
# Required-Stop: $local_fs $remote_fs
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
# Short-Description: Failover for Murmur server on other box
# Description: Failover will fire up a local Murmur instance when needed
### END INIT INFO
#! /bin/sh
# /etc/init.d/murmur-failover.sh
PYTHONBIN=/usr/bin/python
MURMURFAILOVER=/home/murmur/murmur-failover-daemon/murmur-failover-daemon.py

/bin/su - murmur -c "$PYTHONBIN $MURMURFAILOVER $1"
```

Make the file executable: `chmod +x /etc/init.d/murmur-failover.sh`

If you want the service to automatically start on boot, run
`update-rc.d murmur-failover.sh defaults`

### Running the daemon and connecting to the server
To start the daemon if installed as a service run
`service murmur-failover.sh start`

If not installed as a service, go to the folder it was installed and run
`./murmur-failover-daemon.py`

To connect to the server, use the hostname configured to point at the multiple
IP addresses.


## Known shortcomings
Most Mumble clients (or operating systems) will not cycle through the IP
addresses of hostnames with multiple IP addresses. Windows will work fine, but
Linux, Android and possibly other operating systems' clients may have trouble
connecting to the host. A workaround for such clients would be to just use the
IP or hostname of the master Murmur server.


## Maintainer
Oddbjørn Haaland


## License
Licensed under the MIT license (http://opensource.org/licenses/mit-license.html)
