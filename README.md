how to access the blackbox functions:
```curl -X GET "http://localhost:8080/random?number=123"```
```curl -X POST http://localhost:8080/execute-transactions -d "transactions=tx1:10.0,tx2:20.0,tx3:30.5"```
```curl -X POST http://localhost:8080/verify-block -d "transactions=tx1:10.0,tx2:20.0,tx3:30.5&hash=8513313e49b07b21cb3bd005cc48b4d6b75587fc9cd81b8bfdc9d296f22ed531"```


#### VM instructions:

Run the following in the VM to host the Blackbox API:
This code is running on VM 11, IP address: 172.22.150.233 

``` sudo systemctl status firewalld```
   ``` sudo systemctl start firewalld```
    ```sudo systemctl enable firewalld```
    ```sudo firewall-cmd --zone=public --add-port=8080/tcp --permanent```
   ``` sudo firewall-cmd --reload ```
