import requests
import networkx as nx
import matplotlib.pyplot as plt

# Fetching the data from OpenStreetMap API
response = requests.get('https://overpass.kumi.systems/api/interpreter?data=[out:json];area(3600032157)->.searchArea;(node["railway"="station"](area.searchArea);way["railway"="subway"](area.searchArea);relation["railway"="subway"](area.searchArea););out;')

# Parsing the JSON response to get the nodes, edges and their attributes
data = response.json()
nodes = {}
edges = []
for element in data['elements']:
    if element['type'] == 'node':
        nodes[element['id']] = element['tags']['name']
    elif element['type'] == 'way':
        for i in range(len(element['nodes'])-1):
            edges.append((element['nodes'][i], element['nodes'][i+1]))
    elif element['type'] == 'relation':
        for member in element['members']:
            if member['type'] == 'way':
                for i in range(len(member['nodes'])-1):
                    edges.append((member['nodes'][i], member['nodes'][i+1]))

# Creating a networkx graph
shanghai_metro = nx.Graph()
shanghai_metro.add_nodes_from(nodes.keys())
nx.set_node_attributes(shanghai_metro, nodes, 'name')
for edge in edges:
    node1 = edge[0]
    node2 = edge[1]
    pos1 = (data['elements'][list(nodes.keys()).index(node1)]['lon'], data['elements'][list(nodes.keys()).index(node1)]['lat'])
    pos2 = (data['elements'][list(nodes.keys()).index(node2)]['lon'], data['elements'][list(nodes.keys()).index(node2)]['lat'])
    distance = ((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2) ** 0.5
    shanghai_metro.add_edge(node1, node2, weight=distance)

# Visualizing the graph
pos = nx.get_node_attributes(shanghai_metro, 'pos')
plt.figure(figsize=(12, 12))
nx.draw(shanghai_metro, pos=pos, node_color='lightblue', with_labels=True, font_size=8, node_size=100)
nx.draw_networkx_edge_labels(shanghai_metro, pos=pos, font_size=6, edge_labels=nx.get_edge_attributes(shanghai_metro, 'weight'))
plt.show()

