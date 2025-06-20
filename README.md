# LibIPC Python Ctypes Wrapper

A Python ctypes wrapper for libipc - a high-performance inter-process communication (IPC) library using shared memory.

## Features

- **High Performance**: Uses shared memory for fast IPC communication
- **Cross-Platform**: Supports Windows and Linux
- **Multiple Communication Patterns**:
  - **ROUTE**: Single producer, multiple consumers with broadcast
  - **CHANNEL**: Multiple producers, multiple consumers with broadcast
- **Flexible Connection Modes**: SENDER, RECEIVER, or both
- **Timeout Support**: Configurable timeouts for send/receive operations
- **Resource Management**: Automatic cleanup with context managers
- **Thread-Safe**: Safe for use in multi-threaded applications

## Installation

### From Source

```bash
pip install .
```

### Requirements

- Python 3.6+
- libipc.dll (Windows) or libipc.so (Linux) must be available in:
  - The same directory as the Python module
  - System PATH
  - Current working directory

## Quick Start

### Basic Example

```python
from libipc_ctypes import IPCChannel, ChannelType, ConnMode

# Create a sender
with IPCChannel(ChannelType.CHANNEL, "my_channel", ConnMode.SENDER) as sender:
    sender.send(b"Hello, World!")

# Create a receiver
with IPCChannel(ChannelType.CHANNEL, "my_channel", ConnMode.RECEIVER) as receiver:
    data = receiver.receive()
    print(f"Received: {data}")
```

### Convenience Functions

```python
from libipc_ctypes import send_message, receive_message

# Send a single message
send_message("my_channel", b"Hello!")

# Receive a single message
data = receive_message("my_channel", timeout_ms=5000)
```

## API Reference

### Classes

#### `IPCChannel`

Main class for IPC communication.

```python
IPCChannel(channel_type: ChannelType, name: str, mode: ConnMode)
```

**Parameters:**
- `channel_type`: `ChannelType.ROUTE` or `ChannelType.CHANNEL`
- `name`: Unique channel name
- `mode`: `ConnMode.SENDER`, `ConnMode.RECEIVER`, or both

**Methods:**

##### `connect(mode: Optional[ConnMode] = None) -> None`
Connect to the IPC channel.

##### `disconnect() -> None`
Disconnect from the IPC channel.

##### `send(data: Union[bytes, bytearray], timeout_ms: int = 0) -> None`
Send data through the channel.

##### `try_send(data: Union[bytes, bytearray], timeout_ms: int = 0) -> bool`
Try to send data (non-blocking). Returns `True` if successful, `False` on timeout.

##### `receive(timeout_ms: int = 0) -> bytes`
Receive data from the channel.

##### `try_receive() -> Optional[bytes]`
Try to receive data (non-blocking). Returns data or `None` if no data available.

##### `get_receiver_count() -> int`
Get the number of receivers connected to this channel.

##### `wait_for_receivers(count: int, timeout_ms: int = 0) -> bool`
Wait for a specific number of receivers to connect.

##### `close() -> None`
Close the channel and free resources.

**Properties:**
- `is_connected`: Check if the channel is connected
- `is_closed`: Check if the channel is closed

### Enums

#### `ChannelType`
- `ROUTE = 0`: Single producer, multiple consumers with broadcast
- `CHANNEL = 1`: Multiple producers, multiple consumers with broadcast

#### `ConnMode`
- `SENDER = 1`: Send data to the channel
- `RECEIVER = 2`: Receive data from the channel

#### `IPCStatus`
Status codes returned by IPC functions:
- `SUCCESS = 0`
- `ERROR_INVALID_ARGUMENT = -1`
- `ERROR_CONNECTION_FAILED = -2`
- `ERROR_SEND_FAILED = -3`
- `ERROR_RECEIVE_FAILED = -4`
- `ERROR_TIMEOUT = -5`
- `ERROR_MEMORY = -6`

### Functions

#### `clear_channel_storage(name: str) -> None`
Clear IPC storage for a channel by name. Useful for cleanup during development.

#### `send_message(channel_name: str, data: bytes, channel_type: ChannelType = ChannelType.CHANNEL) -> None`
Send a single message and close the channel.

#### `receive_message(channel_name: str, timeout_ms: int = 0, channel_type: ChannelType = ChannelType.CHANNEL) -> bytes`
Receive a single message and close the channel.

### Exceptions

#### `IPCError`
Exception raised for IPC errors. Contains a `status_code` attribute with the underlying error code.

## Usage Examples

### Producer-Consumer Pattern

```python
import threading
import time
from libipc_ctypes import IPCChannel, ChannelType, ConnMode

def producer():
    with IPCChannel(ChannelType.CHANNEL, "data_stream", ConnMode.SENDER) as channel:
        for i in range(10):
            message = f"Data packet {i}".encode()
            channel.send(message)
            time.sleep(0.1)

def consumer():
    with IPCChannel(ChannelType.CHANNEL, "data_stream", ConnMode.RECEIVER) as channel:
        while True:
            try:
                data = channel.receive(timeout_ms=1000)
                print(f"Consumed: {data.decode()}")
            except IPCError as e:
                if e.status_code == IPCStatus.ERROR_TIMEOUT:
                    break
                raise

# Start producer and consumer in separate threads
producer_thread = threading.Thread(target=producer)
consumer_thread = threading.Thread(target=consumer)

consumer_thread.start()
time.sleep(0.1)  # Let consumer start first
producer_thread.start()

producer_thread.join()
consumer_thread.join()
```

### Broadcast to Multiple Receivers

```python
from libipc_ctypes import IPCChannel, ChannelType, ConnMode
import threading

def broadcaster():
    with IPCChannel(ChannelType.ROUTE, "broadcast", ConnMode.SENDER) as channel:
        # Wait for receivers to connect
        channel.wait_for_receivers(2, timeout_ms=5000)
        
        for i in range(5):
            message = f"Broadcast message {i}".encode()
            channel.send(message)
            print(f"Broadcasted: {message.decode()}")

def receiver(receiver_id):
    with IPCChannel(ChannelType.ROUTE, "broadcast", ConnMode.RECEIVER) as channel:
        for _ in range(5):
            data = channel.receive()
            print(f"Receiver {receiver_id} got: {data.decode()}")

# Start receivers
receivers = []
for i in range(2):
    t = threading.Thread(target=receiver, args=(i,))
    t.start()
    receivers.append(t)

# Start broadcaster
broadcaster_thread = threading.Thread(target=broadcaster)
broadcaster_thread.start()

# Wait for completion
broadcaster_thread.join()
for t in receivers:
    t.join()
```

### Error Handling

```python
from libipc_ctypes import IPCChannel, IPCError, IPCStatus, ChannelType, ConnMode

try:
    with IPCChannel(ChannelType.CHANNEL, "test", ConnMode.SENDER) as channel:
        channel.send(b"test data")
except IPCError as e:
    if e.status_code == IPCStatus.ERROR_CONNECTION_FAILED:
        print("Failed to connect to channel")
    elif e.status_code == IPCStatus.ERROR_TIMEOUT:
        print("Operation timed out")
    else:
        print(f"IPC Error: {e}")
```

### Non-blocking Operations

```python
from libipc_ctypes import IPCChannel, ChannelType, ConnMode

with IPCChannel(ChannelType.CHANNEL, "test", ConnMode.SENDER | ConnMode.RECEIVER) as channel:
    # Try to send without blocking
    if channel.try_send(b"test data"):
        print("Data sent successfully")
    else:
        print("Send would block")
    
    # Try to receive without blocking
    data = channel.try_receive()
    if data is not None:
        print(f"Received: {data}")
    else:
        print("No data available")
```

## Troubleshooting

### Common Issues

#### "Could not find libipc.dll"
- Ensure libipc.dll (Windows) or libipc.so (Linux) is in your PATH
- Or place it in the same directory as your Python script
- Or place it in the same directory as the libipc_ctypes module

#### Connection Failed
- Make sure the channel name is unique and valid
- Check that no other process is using the same channel name improperly
- Try clearing the channel storage: `clear_channel_storage("channel_name")`

#### Memory Errors
- Ensure you're properly closing channels or using context managers
- Avoid creating too many channels simultaneously
- Check system shared memory limits

#### Timeout Errors
- Increase timeout values for slow operations
- Check that sender and receiver are using the same channel name and type
- Ensure receiver is started before sender for reliable communication

### Debugging

Enable verbose logging to see what's happening:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Your IPC code here
```

### Performance Tips

1. **Use context managers** (`with` statements) for automatic resource cleanup
2. **Reuse channels** instead of creating new ones for each message
3. **Use try_send/try_receive** for non-blocking operations when appropriate
4. **Choose appropriate timeouts** - not too short (causing unnecessary retries) or too long (blocking the application)
5. **For high-frequency communication**, keep channels open rather than opening/closing repeatedly

## License

This wrapper follows the same license as the underlying libipc library.

## Contributing

Contributions are welcome! Please ensure that:
1. Code follows Python PEP 8 style guidelines
2. New features include appropriate tests
3. Documentation is updated for API changes

## Links

- [libipc GitHub Repository](https://github.com/mutouyun/cpp-ipc)
- [libipc Documentation](https://github.com/mutouyun/cpp-ipc/wiki)
- [Bug Reports](https://github.com/mutouyun/cpp-ipc/issues)
