# Generalised-Tube-Challenge-Solver

Create weighted graph of metro system. Each platform is a node and stations are represented as clusters of nodes - algorithm only needs to visit each cluster once, not every node.

![image](https://user-images.githubusercontent.com/51741333/198717545-ea486566-10e8-4076-809b-981ac225e174.png)

networkx - travelling salesman algo - this would be easy if every station were one node - how to mesh this with Laporte's (2014) platform cluster model?

## Data Source

The data needs to be available for any city and freely usable.

If OSM is used, at a later stage of development I may need to host my own extracts or have some layer of abstraction between the user and the OSM API due to usage limits.

| Data Source       | URL                                     | Availability                               |
|-------------------|-----------------------------------------|--------------------------------------------|
| Mobility Database | https://database.mobilitydata.org/home  | Largely US and EU, little Asian coverage   |
| OpenStreetMap API |                                         |              |

## UI

Initially create a command line interface. Aim to deploy it online.
