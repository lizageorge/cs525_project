# installation/setup
1. make sure go 1.24.2 is installed (see below)
2. `go mod tidy` to install dependencies
3. `go run basic_host.go -port 9000 -peers [comma seperated list of peers]`

# update go to desired version on RHL
```
sudo yum remove golang (y)
```

```
wget https://dl.google.com/go/go1.24.2.linux-amd64.tar.gz
sudo tar -C /usr/local -xzf go1.24.2.linux-amd64.tar.gz
```

```
export PATH=$PATH:/usr/local/go/bin
rm go1.24.2.linux-amd64.tar.gz
source ~/.bashrc
```

confirm installation with `go version` (expecting go version go1.24.2 linux/amd64)


