class argparse {
  package { "argparse":
    ensure => present,
    provider => "pip3",
    require => Package["python3-pip"],
  }
}
