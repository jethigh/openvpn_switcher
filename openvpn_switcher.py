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
        self.server = server

    def in_config(self):
        '''
        Funkcja zwraca True jezeli podany server jest w konfiguracji.
        W przeciwnym przypadku zwraca False
        Funkcja read() dla pliku wczytuje cały plik jako jeden string,
        stąd nie można użyć w re ^ jako początku lini tylko poslużylem
        sie znakiem nowej lini.
        '''
        with open(CONFIG, 'r') as config:
            #match = re.search('^remote ' + str(self.server), config.read())
            match = re.search(r'\nremote ' + self.server, config.read())
            if match:
                return True
            else:
                return False
        config.closed

    def set_config(self):
        '''
        Metoda ustawia te instancje klasy w konfiguracji OpenVPN jako aktywny
        serwer
        '''
        new_content = ''
        if self.in_config():
            print('Serwer ' + self.server + ' jest już w konfiguracji')
        else:
            with open(CONFIG, 'r+') as config:
                for line in config:
                    if re.search(r'^remote ', line):
                        line = re.sub('remote .+ ','remote ' + self.server + ' ',line)
                        new_content += line
                    else:
                        new_content += line
                print(new_content)
                #config.write(new_content)


if __name__ == '__main__':
    serwis = ServiceMonitor('cups')
    server = TZ_Server('de.trust.zone')
    server.set_config()
    #serwis.restart()
