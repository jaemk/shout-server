# shout

> Work in progress server for streaming output to multiple subscribers

## Setup

* Requires `python3.6+`

#### Server

* `pip install -r requirements.txt`
* `python server.py`

#### Client

* `python install -r client-requirements.txt`
* `python client.py --delay 10 bash -c 'for i in {1..10}; do echo "$i"; sleep 1; done'`
  * Go to `output` link displayed

