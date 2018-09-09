#!/usr/bin/python3

import sys
import subprocess
import re

CONFIG='/etc/openvpn/trustzone.conf'

class ServiceMonitor(object):
    def __init__(self, service):
        self.service = service

    def status(self):
        '''
        Metoda zwraca True jezeli podany servis jest uruchomiony
        '''
        cmd = 'sudo systemctl status {}.service'.format(self.service).split()
        proc = subprocess.run(cmd,stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        status = proc.returncode
        if status == 0:
            return True
        else:
            return False

    def start(self):
        '''
        Metoda uruchamia podany serwis
        '''
        cmd = 'sudo systemctl start {}.service'.format(self.service).split()
        if self.status() == False:
            print('Startuje serwis {}'.format(self.service.upper()))
            proc = subprocess.run(cmd,stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            print('Serwis {} jest juz uruchomiony'.format(self.service))

    def stop(self):
        '''
        Metoda zatrzymuje podany serwis
        '''
        cmd = 'sudo systemctl stop {}.service'.format(self.service).split()
        if self.status() == True:
            print('Zatrzymuje serwis {}'.format(self.service.upper()))
            proc = subprocess.run(cmd,stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            print('Serwis {} jest juz zatrzymany'.format(self.service.upper()))

    def restart(self):
        '''
        Metoda restartujaca serwis.
        W rzyczywistowsc wywoluje metody stop oraz start
        '''
        self.stop()
        self.start()

class TZ_Server(object):
    def __init__(self, server):
        sefl.server = server

    def in_config(self):
        '''
        Funkcja zwraca True jezeli podany server jest w konfiguracji.
        W przeciwnym przypadku zwraca False
        '''
        #with open(CONFIG, 'rw') as config:


if __name__ == '__main__':
    serwis = ServiceMonitor('cups')
    serwis.restart()
