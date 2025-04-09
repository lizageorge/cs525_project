# installation/setup
1. make sure go 1.24.2 is installed (see below) on all VMs
2. Run the P2P node on all ten VMs
   1. `go mod tidy` to install dependencies
   2. Make sure you set up a `inputs/peersFile.json` to look like the sample below
   3. In `cmd/p2p-node/`, `go run *.go `
3. Run the desired consensus client on all ten VMs
   1. In `cmd/[algo]-consensus`, `go run main.go`


## Available consensus clients;
- `cmd/ethereum-consensus` for Ethereum-style Proof of Stake


# update go to desired version on RHL the first time (this also installs a versionlock tool and uses it)
I think after running the below commands once, the next time you shut down and open the VM, you just have to update the path and reload the shell anytime you open a new shell. Idk why tho. 
```
sudo yum remove golang -y
wget https://dl.google.com/go/go1.24.2.linux-amd64.tar.gz
sudo tar -C /usr/local -xzf go1.24.2.linux-amd64.tar.gz
rm go1.24.2.linux-amd64.tar.gz
echo "export PATH=$PATH:/usr/local/go/bin" >> ~/.bash_profile
sudo dnf install 'dnf-command(versionlock)' -y
sudo dnf versionlock add golang
source ~/.bashrc
source ~/.bash_profile
```

confirm installation with `go version` (expecting go version go1.24.2 linux/amd64)


# sample peersFile.json
```
{
    "vmName": "vm02",
    "vmPeers": [
        {
            "addr": "/ip4/172.22.154.250/tcp/9000/p2p/12D3KooWJpgCgvPTaCtmCrixW7TAMggrEPzRvCRWqTzdWkhMMGG9",
            "name": "vm01"
        }
    ]
}
```
