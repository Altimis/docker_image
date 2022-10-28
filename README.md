# Pipeline
**NOTE** : All setup steps are specified in the setup.sh bash script. 
Create a bash script in ~ folder and copy and paste then run it using the command `source setup.sh` 

In order to run the app in ec2 instance (ubuntu 20.04) we need to install the following requirements:  
- Python (version>3.7)
- Git
- Clone the repo containing the app from git
- Install Google Chrome and Chromedriver
- Install required python libraries to run the app
- Setup the AWS credentials for an account that has full access to S3 and SES services

## Install git 
`sudo apt-get update`  
`sudo apt install git-all`
## Install python 3
Python 3.10 is preinstalled. Run `python3 --version` to verify
## Install pip3
`sudo apt-get update`  
`sudo apt-get -y install python3-pip` (click enter if the instance wants to restart some services)

## Setup S3
Create .aws folder : `mkdir .aws`  
Locate to .aws folder : `cd .aws`  
Create credentials file : `touch credentials`  
Edit credentials file : `nano credentials`  

Insert the following with actual key pair:  
[default]  
aws_access_key_id = YOUR_ACCESS_KEY  
aws_secret_access_key = YOUR_SECRET_KEY  

Create config file : `touch config`  
Edit config file : `nano config`   

Insert region:  
[default]  
region=us-east-2  

Now AWS credentials are setup to the ec2 instance. 
The App can access S3 and SES if the account has the needed permissions.

Go back to ~ folder : `cd ..`  
## Clone repo
`git clone https://github.com/Altimis/docker_image.git`
## Locate to working directory
`cd docker_image`
## Install chrome browser
`wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -`  

`sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'`  

`sudo apt-get -y update`  

`sudo apt-get install -y google-chrome-stable`

verify if google-chrome 106 is installed : `google-chrome-stable --version`

## Install chromedriver
`sudo apt-get install -yqq unzip`  

``wget -O /tmp/chromedriver.zip http://chromedriver.storage.googleapis.com/`curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE`/chromedriver_linux64.zip``

`sudo unzip /tmp/chromedriver.zip chromedriver -d /usr/local/bin/`  

`sudo chmod 0777 /usr/local/bin/chromedriver`  

## Install required Python libraries
`pip install -r requirements.txt`

## Run the script directly 
`python3 app.py`

## Schedule the script using crontab
### run script at boot using crontab
ref : https://www.linuxshelltips.com/run-python-script-ubuntu-startup/  

To do so, run the command : `crontab -e` (choose nano for editor)  
And then add the following command at the end of the file :  
`@reboot python3 /home/ubuntu/docker_image/app.py &`  
This will run the script app.py in each reboot. & means that the script will wait ubuntu to fully start up.




