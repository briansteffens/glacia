#!/usr/bin/env bash

apt-get update
apt-get install -y squid-deb-proxy-client

# python
apt-get install -y python3 libpython3-dev python3-pip
pip3 install pymysql

# mysql-server
echo mysql-server mysql-server/root_password password rootpass | sudo debconf-set-selections
echo mysql-server mysql-server/root_password_again password rootpass | sudo debconf-set-selections
apt-get install -y mysql-server
mysql --user=root --password=rootpass --execute="drop database if exists __glacia; create database __glacia;"
mysql --user=root --password=rootpass __glacia < "/vagrant/vagrant/__glacia.sql"

# git
apt-get install -y git

# app config
echo 'PYTHONPATH="/vagrant"' >> /home/vagrant/.bashrc
echo 'export PYTHONPATH' >> /home/vagrant/.bashrc