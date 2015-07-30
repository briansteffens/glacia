Exec { path => [ "/bin/", "/sbin/" , "/usr/bin/", "/usr/sbin/" ] }

include system-update
include squid-proxy
include python3
include pymysql

class { "::mysql::server":
  require => Class['squid-proxy'],
}

mysql::db { 'glacia':
  user => 'glacia',
  password => 'pass',
  host => 'localhost',
  grant => ['SELECT', 'INSERT', 'UPDATE', 'DELETE'],
  sql => '/vagrant/vagrant/glacia.sql',
}

file { '/etc/glacia.conf':
  ensure => 'link',
  target => '/vagrant/vagrant/glacia.conf',
}

file { '/home/vagrant/.bashrc':
  ensure => 'link',
  target => '/vagrant/vagrant/bashrc',
}
