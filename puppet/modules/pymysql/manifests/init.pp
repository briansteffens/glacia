class pymysql {
  package { "pymysql":
    ensure => present,
    provider => "pip3",
    require => Package["python3-pip"],
  }
}
