#           MQTT mapper plugin (inspired from MQTT discovery plugin)
#
"""
<plugin key="MqttMapper" name="MQTT mapper with LAN interface" author="Flying Domotic" version="0.0.5">
    <description>
      MQTT mapper plug-in<br/><br/>
      Maps MQTT topics to Domoticz devices<br/>
    </description>
    <params>
        <param field="Address" label="MQTT Server address" width="300px" required="true" default="127.0.0.1"/>
        <param field="Port" label="Port" width="300px" required="true" default="1883"/>
        <param field="Username" label="Username" width="300px"/>
        <param field="Password" label="Password" width="300px" password="true"/>
        <param field="Mode1" label="JSON mapping file to use" width="400px" required="true" default="MqttMapper.json"/>
        <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="Extra verbose (Framework logs 2+4+8+16+64 + device dump)" value="Verbose+"/>
                <option label="Verbose (Framework logs 2+4+8+16+64)" value="Verbose"/>
                <option label="Normal (Framework logs 2+4+8)" value="Debug"/>
                <option label="None" value="Normal" default="true"/>
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
from datetime import datetime
from itertools import count, filterfalse
import json
import time
import traceback

class MqttClient:
    Address = ""
    Port = ""
    mqttConn = None
    isConnected = False
    mqttConnectedCb = None
    mqttDisconnectedCb = None
    mqttPublishCb = None

    def __init__(self, destination, port, mqttConnectedCb, mqttDisconnectedCb, mqttPublishCb, mqttSubackCb):
        Domoticz.Debug("MqttClient::__init__")
        self.Address = destination
        self.Port = port
        self.mqttConnectedCb = mqttConnectedCb
        self.mqttDisconnectedCb = mqttDisconnectedCb
        self.mqttPublishCb = mqttPublishCb
        self.mqttSubackCb = mqttSubackCb
        self.Open()

    def __str__(self):
        Domoticz.Debug("MqttClient::__str__")
        if (self.mqttConn != None):
            return str(self.mqttConn)
        else:
            return "None"

    def Open(self):
        Domoticz.Debug("MqttClient::Open")
        if (self.mqttConn != None):
            self.Close()
        self.isConnected = False
        self.mqttConn = Domoticz.Connection(Name=self.Address, Transport="TCP/IP", Protocol="MQTT", Address=self.Address, Port=self.Port)
        self.mqttConn.Connect()

    def Connect(self):
        Domoticz.Debug("MqttClient::Connect")
        if (self.mqttConn == None):
            self.Open()
        else:
            ID = 'Domoticz_'+Parameters['Key']+'_'+str(Parameters['HardwareID'])+'_'+str(int(time.time()))
            Domoticz.Log("MQTT CONNECT ID: '" + ID + "'")
            self.mqttConn.Send({'Verb': 'CONNECT', 'ID': ID})

    def Ping(self):
        #Domoticz.Debug("MqttClient::Ping")
        if (self.mqttConn == None or not self.isConnected):
            self.Open()
        else:
            self.mqttConn.Send({'Verb': 'PING'})

    def Publish(self, topic, payload, retain = 0):
        Domoticz.Debug("MqttClient::Publish " + topic + " (" + payload + ")")
        if (self.mqttConn == None or not self.isConnected):
            self.Open()
        else:
            self.mqttConn.Send({'Verb': 'PUBLISH', 'Topic': topic, 'Payload': bytearray(payload, 'utf-8'), 'Retain': retain})

    def Subscribe(self, topics):
        Domoticz.Debug("MqttClient::Subscribe")
        subscriptionlist = []
        for topic in topics:
            subscriptionlist.append({'Topic':topic, 'QoS':0})
        if (self.mqttConn == None or not self.isConnected):
            self.Open()
        else:
            self.mqttConn.Send({'Verb': 'SUBSCRIBE', 'Topics': subscriptionlist})

    def Close(self):
        Domoticz.Log("MqttClient::Close")
        #TODO: Disconnect from server
        self.mqttConn = None
        self.isConnected = False

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("MqttClient::onConnect")
        if (Status == 0):
            Domoticz.Log("Successful connect to: "+Connection.Address+":"+Connection.Port)
            self.Connect()
        else:
            Domoticz.Error("Failed to connect to: "+Connection.Address+":"+Connection.Port+", Description: "+Description)

    def onDisconnect(self, Connection):
        Domoticz.Log("MqttClient::onDisonnect Disconnected from: "+Connection.Address+":"+Connection.Port)
        self.Close()
        # TODO: Reconnect?
        if self.mqttDisconnectedCb != None:
            self.mqttDisconnectedCb()

    def onMessage(self, Connection, Data):
        topic = ''
        if 'Topic' in Data:
            topic = Data['Topic']
        payloadStr = ''
        if 'Payload' in Data:
            payloadStr = Data['Payload'].decode('utf8','replace')
            payloadStr = str(payloadStr.encode('unicode_escape'))

        if Data['Verb'] == "CONNACK":
            self.isConnected = True
            if self.mqttConnectedCb != None:
                self.mqttConnectedCb()

        if Data['Verb'] == "SUBACK":
            if self.mqttSubackCb != None:
                self.mqttSubackCb()

        if Data['Verb'] == "PUBLISH":
            if self.mqttPublishCb != None:
                self.mqttPublishCb(topic, Data['Payload'])

class BasePlugin:
    # MQTT settings
    mqttClient = None
    mqttserveraddress = ""
    mqttserverport = ""
    debugging = "Normal"
    jsonData = None

    # Returns a dictionary value giving a key or default value if not existing
    def getValue(self, dict, key, default=''):
        if dict == None:
            return default
        else:
            if key in dict:
                if dict[key] == None:
                    return default #or None
                else:
                    return dict[key]
            else:
                return default #or None

    # Return a path in a dictionary or default value if not existing
    def getPathValue (self, dict, path, separator = '/', default=''):
        pathElements = path.split(separator)
        element = dict
        for pathElement in pathElements:
            if pathElement not in element:
                return default
            element = element[pathElement]
        return element

    def getDevice(self, deviceName):
        # Find a device by name in devices table
        for device in Devices:
            if (Devices[device].DeviceID == deviceName) :
                # Return device
                return Devices[device]
        # Return None if not found
        return None

    def getNextDeviceId(self):
        # Get next free device Id
        nextDeviceId = 1
        while True:
            exists = False
            for device in Devices:
                if (device == nextDeviceId) :
                    exists = True
                    break
            if (not exists):
                break;
            nextDeviceId = nextDeviceId + 1
        return nextDeviceId

    def deviceStr(self, unit):
        name = "<UNKNOWN>"
        if unit in Devices:
            name = Devices[unit].Name
        return format(unit, '03d') + "/" + name

    def getUnit(self, device):
        unit = -1
        for k, dev in Devices.items():
            if dev == device:
                unit = k
        return unit

    def onStart(self):
        # Parse options
        self.debugging = Parameters["Mode6"]
        DumpConfigToLog()
        if self.debugging == "<!--Verbose+-->":
            Domoticz.Debugging(2+4+8+16+64)
        if self.debugging == "Verbose":
            Domoticz.Debugging(2+4+8+16+64)
        if self.debugging == "Debug":
            Domoticz.Debugging(2+4+8)
        self.mqttserveraddress = Parameters["Address"].replace(" ", "")
        self.mqttserverport = Parameters["Port"].replace(" ", "")

        # Load JSON mapping file
        jsonFile = Parameters['HomeFolder'] + Parameters["Mode1"]
        self.jsonData = None
        with open(jsonFile, encoding = 'UTF-8') as configStream:
            self.jsonData = json.load(configStream)

        # Go through Json file to create devices
        for node in self.jsonData.items():
            nodeName = node[0]
            nodeItems = node[1]
            nodeTopic = self.getValue(nodeItems, 'topic', None)
            nodeType = self.getValue(nodeItems, 'type', None)
            nodeSubtype = self.getValue(nodeItems, 'subtype', None)
            nodeSwitchtype = self.getValue(nodeItems, 'switchtype', "0")
            nodeOptions  = self.getValue(nodeItems, 'options', None)

            if nodeName != None and nodeTopic != None and nodeType != None and nodeSubtype != None:
                # Create device if needed
                if (self.getDevice(nodeTopic) == None):
                    Domoticz.Log("Creating device " + nodeName)
                    Domoticz.Device(Name=nodeName, Unit=self.getNextDeviceId(), Type=int(nodeType), Subtype=int(nodeSubtype), Switchtype=int(nodeSwitchtype), DeviceID=nodeTopic, Options=nodeOptions, Used=True).Create()
        # Connect to MQTT server
        self.mqttClient = MqttClient(self.mqttserveraddress, self.mqttserverport, self.onMQTTConnected, self.onMQTTDisconnected, self.onMQTTPublish, self.onMQTTSubscribed)

        # Enable heartbeat
        Domoticz.Heartbeat(60)

    def onConnect(self, Connection, Status, Description):
        self.mqttClient.onConnect(Connection, Status, Description)

    def onDisconnect(self, Connection):
        self.mqttClient.onDisconnect(Connection)

    def onMessage(self, Connection, Data):
        self.mqttClient.onMessage(Connection, Data)

    def onMQTTConnected(self):
        Domoticz.Debug("onMQTTConnected")
        self.mqttClient.Subscribe(self.getTopics())

    def onMQTTDisconnected(self):
        Domoticz.Debug("onMQTTDisconnected")

    def onMQTTPublish(self, topic, rawmessage):
        message = ""
        try:
            message = json.loads(rawmessage.decode('utf8'))
        except ValueError:
            message = rawmessage.decode('utf8')

        topiclist = topic.split('/')
        if self.debugging == "Verbose+":
            DumpMQTTMessageToLog(topic, rawmessage, 'onMQTTPublish: ')

        device = self.getDevice(topic)
        if (device != None):
            Domoticz.Debug("onMQTTConnected found "+str(topic)+", Device '" + device.Name + "'")
            # Iterating through the JSON list
            for node in self.jsonData.items():
                nodeItems = node[1]
                nodeTopic = self.getValue(nodeItems, 'topic', None) # Get MQTT topic
                if nodeTopic == topic:  # Is this the rigt topic?
                    nodeType = self.getValue(nodeItems, 'type', None)   # Read some values for this device
                    nodeMapping = self.getValue(nodeItems, 'mapping', None)
                    mappingItem = self.getValue(nodeMapping, 'item', None)
                    mappingDefault = self.getValue(nodeMapping, 'default', None)
                    mappingValues = self.getValue(nodeMapping, 'values', None)
                    valueToSet = None
                    if mappingItem !=None:
                        if mappingItem == '':   # Empty mapping means (not json) full message
                            readValue = str(message)
                        else:   # This is a json payload
                            readValue = ''
                            items = mappingItem.split(';')  # Work with multiple items values
                            for item in items:  # Read all values to map
                                readValue += ";"# Add ';' as separator
                                if item[0:1] == '~': # Insert every item starting with '~' as is
                                    readValue += item[1:]   # Add item minus '~'
                                else:
                                    itemValue = self.getPathValue(message, item, '/', None) # Extract value from message
                                    if itemValue == None:
                                        Domoticz.Error('Can\'t find "'+str(item)+'" in "'+str(message)+'"')
                                    else:   # Add extracted value
                                        readValue += str(itemValue)
                            readValue = readValue[1:]   # Remove first ';'
                        if nodeType == '244':   # This is a switch
                            if  mappingDefault != None and mappingValues != None:
                                valueToSet = mappingDefault # Set default mapping
                                for testValue in mappingValues: # Scan all mapping values
                                    if testValue == readValue:  # Is this the same value?
                                        valueToSet = mappingValues[testValue]   # Insert mapped value
                            else:
                                Domoticz('Bad mapping for '+device.Name)
                        else:   # Not a switch
                            valueToSet = readValue
                    else:   # No mapping given
                        Domoticz('No mapping for '+device.Name)
                    if valueToSet != None: # Value given, set it
                        if valueToSet.isnumeric():  # Set nValue and sValue depending on value type (numeric or not)
                            Domoticz.Log('Setting '+device.Name+' to '+valueToSet)  # Value is numeric
                            device.Update(nValue=int(valueToSet), sValue=str(readValue))   # For numeric mapped values, sValue is original payload (part)
                        else:   # Value is not numeric
                            Domoticz.Log('Setting '+device.Name+' to "'+valueToSet+'"') 
                            device.Update(nValue=0, sValue=str(valueToSet))

    def onMQTTSubscribed(self):
        # (Re)subscribed, refresh device info
        Domoticz.Debug("onMQTTSubscribed")
        topics = set()

# ==========================================================DASHBOARD COMMAND=============================================================
    def onCommand(self, Unit, Command, Level, sColor):
        Domoticz.Log(self.deviceStr(Unit) + ": Command: '" + str(Command) + "', Level: " + str(Level) + ", Color:" + str(sColor) + " ** not supported **")

    def onDeviceAdded(self, Unit):
        Domoticz.Log("onDeviceAdded " + self.deviceStr(Unit))
        return

    def onDeviceModified(self, Unit):
        Domoticz.Log("onDeviceModified " + self.deviceStr(Unit))
        
    def onDeviceRemoved(self, Unit):
        Domoticz.Log("onDeviceRemoved " + self.deviceStr(Unit))

    def onHeartbeat(self):
        if self.debugging == "Verbose" or self.debugging == "Verbose+":
            Domoticz.Debug("Heartbeating...")

        # Reconnect if connection has dropped
        if self.mqttClient.mqttConn is None or (not self.mqttClient.mqttConn.Connecting() and not self.mqttClient.mqttConn.Connected() or not self.mqttClient.isConnected):
            Domoticz.Debug("Reconnecting")
            self.mqttClient.Open()
        else:
            self.mqttClient.Ping()

    # Returns list of topics to subscribe to
    def getTopics(self):
        topics = set()
        for device in Devices:
            topics.add(Devices[device].DeviceID)
        Domoticz.Debug("getTopics: '" + str(topics) +"'")
        return list(topics)

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Color):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Color)

def onDeviceAdded(Unit):
    global _plugin
    _plugin.onDeviceAdded(Unit)

def onDeviceModified(Unit):
    global _plugin
    _plugin.onDeviceModified(Unit)

def onDeviceRemoved(Unit):
    global _plugin
    _plugin.onDeviceRemoved(Unit)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Log( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Log("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Log("Device: " + str(x) + " - " + str(Devices[x]))
    return

def DumpMQTTMessageToLog(topic, rawmessage, prefix=''):
    message = rawmessage.decode('utf8','replace')
    message = str(message.encode('unicode_escape'))
    Domoticz.Log(prefix+topic+":"+message)