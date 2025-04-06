# installation/setup
1. make sure go 1.24.2 is installed (see below)
2. `go mod tidy` to install dependencies
3. Make sure you set up a `peer2File.json` to look like the sample below
4. `go run node.go `

# update go to desired version on RHL (this also installs a versionlock tool and uses it, but sadly that didn't work as I tht it would)
```
sudo yum remove golang -y
```

```
wget https://dl.google.com/go/go1.24.2.linux-amd64.tar.gz
sudo tar -C /usr/local -xzf go1.24.2.linux-amd64.tar.gz
```

```
export PATH=$PATH:/usr/local/go/bin
rm go1.24.2.linux-amd64.tar.gz
source ~/.bashrc
sudo dnf install 'dnf-command(versionlock)' -y
sudo dnf versionlock add golang
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