Vagrant.configure(2) do |config|
    config.vm.box = "ubuntu/trusty64"

    config.vm.define "glacia" do |glacia|
        glacia.vm.hostname = "glacia.vm"
        glacia.vm.network "public_network"

        glacia.vm.provider :virtualbox do |vb|
            vb.customize ["modifyvm", :id, "--memory", 2048]
        end

        glacia.vm.provision :shell, path: "vagrant/setup.sh"
    end
end