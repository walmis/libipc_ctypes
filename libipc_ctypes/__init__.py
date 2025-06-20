"""
LibIPC ctypes wrapper for Windows

This module provides a Python ctypes wrapper for libipc.dll, enabling
inter-process communication using shared memory.

Usage:
    from libipc_ctypes import IPCChannel, ChannelType, ConnMode
    
    # Create a sender
    sender = IPCChannel(ChannelType.CHANNEL, "test_channel", ConnMode.SENDER)
    sender.connect()
    sender.send(b"Hello, World!")
    
    # Create a receiver  
    receiver = IPCChannel(ChannelType.CHANNEL, "test_channel", ConnMode.RECEIVER)
    receiver.connect()
    data = receiver.receive()
    print(data)
"""

import ctypes
import ctypes.util
from ctypes import c_void_p, c_char_p, c_int, c_size_t, c_uint64, POINTER, Structure
from enum import IntEnum
import os
from typing import Optional, Union


class ChannelType(IntEnum):
    """IPC Channel types"""
    ROUTE = 0      # Single producer, multiple consumers with broadcast
    CHANNEL = 1    # Multiple producers, multiple consumers with broadcast


class ConnMode(IntEnum):
    """Connection mode flags"""
    SENDER = 1
    RECEIVER = 2


class IPCStatus(IntEnum):
    """Status codes returned by IPC functions"""
    SUCCESS = 0
    ERROR_INVALID_ARGUMENT = -1
    ERROR_CONNECTION_FAILED = -2
    ERROR_SEND_FAILED = -3
    ERROR_RECEIVE_FAILED = -4
    ERROR_TIMEOUT = -5
    ERROR_MEMORY = -6


class IPCBuffer(Structure):
    """Buffer structure to hold received data"""
    _fields_ = [
        ("data", c_void_p),
        ("size", c_size_t),
        ("free_fn", c_void_p),  # Function pointer
        ("ctx", c_void_p)
    ]


class IPCError(Exception):
    """Exception raised for IPC errors"""
    
    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        status_names = {
            IPCStatus.ERROR_INVALID_ARGUMENT.value: "Invalid argument",
            IPCStatus.ERROR_CONNECTION_FAILED.value: "Connection failed", 
            IPCStatus.ERROR_SEND_FAILED.value: "Send failed",
            IPCStatus.ERROR_RECEIVE_FAILED.value: "Receive failed",
            IPCStatus.ERROR_TIMEOUT.value: "Timeout",
            IPCStatus.ERROR_MEMORY.value: "Memory error"
        }
        status_name = status_names.get(status_code, f"Unknown error ({status_code})")
        super().__init__(f"{status_name}: {message}" if message else status_name)


def _load_library():
    """Load the libipc.dll library"""
    # Try different possible locations for the DLL
    possible_paths = [
        "libipc.dll",  # Current directory
        os.path.join(os.path.dirname(__file__), "libipc.dll"),
    ]
    
    # Also try system PATH
    lib_name = ctypes.util.find_library("libipc")
    if lib_name:
        possible_paths.append(lib_name)
    
    for path in possible_paths:
        try:
            return ctypes.CDLL(path)
        except (OSError, FileNotFoundError):
            continue
    
    raise RuntimeError(
        "Could not find libipc.dll. Please ensure it's in your PATH or "
        "in the same directory as this module."
    )


# Load the library
_lib = _load_library()

# Define function signatures
_lib.ipc_channel_create.argtypes = [c_int, c_char_p, c_int]
_lib.ipc_channel_create.restype = c_void_p

_lib.ipc_channel_destroy.argtypes = [c_void_p]
_lib.ipc_channel_destroy.restype = None

_lib.ipc_channel_connect.argtypes = [c_void_p, c_int]
_lib.ipc_channel_connect.restype = c_int

_lib.ipc_channel_disconnect.argtypes = [c_void_p]
_lib.ipc_channel_disconnect.restype = c_int

_lib.ipc_channel_send.argtypes = [c_void_p, c_void_p, c_size_t, c_uint64]
_lib.ipc_channel_send.restype = c_int

_lib.ipc_channel_try_send.argtypes = [c_void_p, c_void_p, c_size_t, c_uint64]
_lib.ipc_channel_try_send.restype = c_int

_lib.ipc_channel_recv.argtypes = [c_void_p, POINTER(IPCBuffer), c_uint64]
_lib.ipc_channel_recv.restype = c_int

_lib.ipc_channel_try_recv.argtypes = [c_void_p, POINTER(IPCBuffer)]
_lib.ipc_channel_try_recv.restype = c_int

_lib.ipc_buffer_free.argtypes = [POINTER(IPCBuffer)]
_lib.ipc_buffer_free.restype = None

_lib.ipc_channel_recv_count.argtypes = [c_void_p]
_lib.ipc_channel_recv_count.restype = c_int

_lib.ipc_channel_wait_for_recv.argtypes = [c_void_p, c_size_t, c_uint64]
_lib.ipc_channel_wait_for_recv.restype = c_int

_lib.ipc_channel_clear_storage.argtypes = [c_char_p]
_lib.ipc_channel_clear_storage.restype = None


def _get_buffer_pointer(data: Union[bytes, bytearray]) -> c_void_p:
    """Get a ctypes pointer to buffer data"""
    if isinstance(data, bytes):
        # For bytes, create a c_char_p and cast to void*
        return ctypes.cast(ctypes.c_char_p(data), c_void_p)
    elif isinstance(data, bytearray):
        # For bytearray, use from_buffer to get a pointer
        return ctypes.cast((ctypes.c_char * len(data)).from_buffer(data), c_void_p)
    else:
        raise TypeError("Data must be bytes or bytearray")


class IPCChannel:
    """
    High-level wrapper for IPC channel operations
    
    This class provides a Pythonic interface to the libipc library,
    handling resource management and error checking automatically.
    """
    
    def __init__(self, channel_type: ChannelType, name: str, mode: ConnMode):
        """
        Create a new IPC channel
        
        Args:
            channel_type: Type of channel (ROUTE or CHANNEL)
            name: Channel name (must be unique per system)
            mode: Connection mode (SENDER, RECEIVER, or SENDER|RECEIVER)
        
        Raises:
            IPCError: If channel creation fails
        """
        self.name = name
        self.channel_type = channel_type
        self.mode = mode
        self._handle = None
        self._connected = True
        
        name_bytes = name.encode('utf-8')
        handle = _lib.ipc_channel_create(int(channel_type), name_bytes, int(mode))
        
        if not handle:
            raise IPCError(IPCStatus.ERROR_CONNECTION_FAILED, f"Failed to create channel '{name}'")
        
        self._handle = handle
    
    def __del__(self):
        """Destructor - automatically cleanup resources"""
        self.close()
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
    
    def connect(self, mode: Optional[ConnMode] = None) -> None:
        """
        Connect to the IPC channel
        
        Args:
            mode: Connection mode (defaults to mode specified in constructor)
            
        Raises:
            IPCError: If connection fails
        """
        if not self._handle:
            raise IPCError(IPCStatus.ERROR_INVALID_ARGUMENT, "Channel is closed")
        
        if self._connected:
            return
        
        connect_mode = int(mode) if mode is not None else int(self.mode)
        print(f"Connecting to channel '{self.name}' with mode {connect_mode}")
        result = _lib.ipc_channel_connect(self._handle, connect_mode)
        
        if result != IPCStatus.SUCCESS:
            raise IPCError(result, f"Failed to connect to channel '{self.name}'")
        
        self._connected = True
    
    def disconnect(self) -> None:
        """
        Disconnect from the IPC channel
        
        Raises:
            IPCError: If disconnection fails
        """
        if not self._handle or not self._connected:
            return
        
        result = _lib.ipc_channel_disconnect(self._handle)
        
        if result != IPCStatus.SUCCESS:
            raise IPCError(result, f"Failed to disconnect from channel '{self.name}'")
        
        self._connected = False
    
    def send(self, data: Union[bytes, bytearray], timeout_ms: int = 0) -> None:
        """
        Send data through the channel
        
        Args:
            data: Data to send (bytes or bytearray)
            timeout_ms: Timeout in milliseconds (0 for default)
            
        Raises:
            IPCError: If send fails
        """
        if not self._handle:
            raise IPCError(IPCStatus.ERROR_INVALID_ARGUMENT, "Channel is closed")
        
        if not self._connected:
            raise IPCError(IPCStatus.ERROR_CONNECTION_FAILED, "Channel not connected")
        
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Data must be bytes or bytearray")
        
        data_ptr = _get_buffer_pointer(data)
        result = _lib.ipc_channel_send(
            self._handle, 
            data_ptr, 
            len(data), 
            timeout_ms
        )
        
        if result != IPCStatus.SUCCESS:
            raise IPCError(result, "Failed to send data")
    
    def try_send(self, data: Union[bytes, bytearray], timeout_ms: int = 0) -> bool:
        """
        Try to send data (non-blocking, won't force push on timeout)
        
        Args:
            data: Data to send (bytes or bytearray)
            timeout_ms: Timeout in milliseconds (0 for default)
            
        Returns:
            True if sent successfully, False if timeout
            
        Raises:
            IPCError: If send fails for reasons other than timeout
        """
        if not self._handle:
            raise IPCError(IPCStatus.ERROR_INVALID_ARGUMENT, "Channel is closed")
        
        if not self._connected:
            raise IPCError(IPCStatus.ERROR_CONNECTION_FAILED, "Channel not connected")
        
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Data must be bytes or bytearray")
        
        data_ptr = _get_buffer_pointer(data)
        result = _lib.ipc_channel_try_send(
            self._handle, 
            data_ptr, 
            len(data), 
            timeout_ms
        )
        
        if result == IPCStatus.SUCCESS:
            return True
        elif result == IPCStatus.ERROR_TIMEOUT:
            return False
        else:
            raise IPCError(result, "Failed to send data")
    
    def receive(self, timeout_ms: int = 0) -> bytes:
        """
        Receive data from the channel
        
        Args:
            timeout_ms: Timeout in milliseconds (0 for default)
            
        Returns:
            Received data as bytes
            
        Raises:
            IPCError: If receive fails
        """
        if not self._handle:
            raise IPCError(IPCStatus.ERROR_INVALID_ARGUMENT, "Channel is closed")
        
        if not self._connected:
            raise IPCError(IPCStatus.ERROR_CONNECTION_FAILED, "Channel not connected")
        
        buffer = IPCBuffer()
        result = _lib.ipc_channel_recv(self._handle, ctypes.byref(buffer), timeout_ms)
        
        if result != IPCStatus.SUCCESS:
            raise IPCError(result, "Failed to receive data")
        
        try:
            # Copy data from buffer
            data = ctypes.string_at(buffer.data, buffer.size)
            return data
        finally:
            # Free the buffer
            _lib.ipc_buffer_free(ctypes.byref(buffer))
    
    def try_receive(self) -> Optional[bytes]:
        """
        Try to receive data (non-blocking)
        
        Returns:
            Received data as bytes, or None if no data available
            
        Raises:
            IPCError: If receive fails for reasons other than timeout
        """
        if not self._handle:
            raise IPCError(IPCStatus.ERROR_INVALID_ARGUMENT, "Channel is closed")
        
        if not self._connected:
            raise IPCError(IPCStatus.ERROR_CONNECTION_FAILED, "Channel not connected")
        
        buffer = IPCBuffer()
        result = _lib.ipc_channel_try_recv(self._handle, ctypes.byref(buffer))
        
        if result == IPCStatus.SUCCESS:
            try:
                # Copy data from buffer
                data = ctypes.string_at(buffer.data, buffer.size)
                return data
            finally:
                # Free the buffer
                _lib.ipc_buffer_free(ctypes.byref(buffer))
        elif result == IPCStatus.ERROR_TIMEOUT:
            return None
        else:
            raise IPCError(result, "Failed to receive data")
    
    def get_receiver_count(self) -> int:
        """
        Get the number of receivers connected to this channel
        
        Returns:
            Number of receivers, or -1 on error
        """
        if not self._handle:
            return -1
        
        return _lib.ipc_channel_recv_count(self._handle)
    
    def wait_for_receivers(self, count: int, timeout_ms: int = 0) -> bool:
        """
        Wait for a specific number of receivers to connect
        
        Args:
            count: Number of receivers to wait for
            timeout_ms: Timeout in milliseconds (0 for no timeout)
            
        Returns:
            True if successful, False on timeout
            
        Raises:
            IPCError: If wait fails
        """
        if not self._handle:
            raise IPCError(IPCStatus.ERROR_INVALID_ARGUMENT, "Channel is closed")
        
        result = _lib.ipc_channel_wait_for_recv(self._handle, count, timeout_ms)
        
        if result == 1:
            return True
        elif result == 0:
            return False
        else:
            raise IPCError(IPCStatus.ERROR_CONNECTION_FAILED, "Failed to wait for receivers")
    
    def close(self) -> None:
        """Close the channel and free resources"""
        if self._handle:
            if self._connected:
                try:
                    self.disconnect()
                except IPCError:
                    pass  # Ignore disconnect errors during cleanup
            
            _lib.ipc_channel_destroy(self._handle)
            self._handle = None
            self._connected = False
    
    @property
    def is_connected(self) -> bool:
        """Check if the channel is connected"""
        return self._connected and self._handle is not None
    
    @property  
    def is_closed(self) -> bool:
        """Check if the channel is closed"""
        return self._handle is None


def clear_channel_storage(name: str) -> None:
    """
    Clear IPC storage for a channel by name
    
    This is useful for cleaning up after channels that weren't
    properly closed, especially during development/testing.
    
    Args:
        name: Channel name to clear
    """
    name_bytes = name.encode('utf-8')
    _lib.ipc_channel_clear_storage(name_bytes)


# Convenience functions for simple use cases
def send_message(channel_name: str, data: bytes, channel_type: ChannelType = ChannelType.CHANNEL) -> None:
    """
    Send a single message and close the channel
    
    Args:
        channel_name: Name of the channel
        data: Data to send
        channel_type: Type of channel to create
    """
    with IPCChannel(channel_type, channel_name, ConnMode.SENDER) as channel:
        channel.connect()
        channel.send(data)


def receive_message(channel_name: str, timeout_ms: int = 0, 
                   channel_type: ChannelType = ChannelType.CHANNEL) -> bytes:
    """
    Receive a single message and close the channel
    
    Args:
        channel_name: Name of the channel
        timeout_ms: Timeout in milliseconds
        channel_type: Type of channel to create
        
    Returns:
        Received data
    """
    with IPCChannel(channel_type, channel_name, ConnMode.RECEIVER) as channel:
        channel.connect()
        return channel.receive(timeout_ms)


if __name__ == "__main__":
    # Simple test/demo
    import threading
    import time
    
    def sender_func():
        """Test sender"""
        time.sleep(0.1)  # Let receiver start first
        try:
            with IPCChannel(ChannelType.CHANNEL, "test_channel", ConnMode.SENDER) as chan:
                for i in range(5):
                    message = f"Hello {i}".encode()
                    chan.send(message)
                    print(f"Sent: {message}")
                    time.sleep(0.5)
        except IPCError as e:
            print(f"Sender error: {e}")
    
    def receiver_func():
        """Test receiver"""
        try:
            with IPCChannel(ChannelType.CHANNEL, "test_channel", ConnMode.RECEIVER) as chan:
                for _ in range(5):
                    try:
                        data = chan.receive(1000)  # 1 second timeout
                        print(f"Received: {data}")
                    except IPCError as e:
                        print(f"Receive error: {e} {e.status_code}")
                        continue
                    
        except IPCError as e:
            print(f"Receiver error: {e}")
            
    
    print("Running IPC test...")
    
    # Clear any existing storage
    clear_channel_storage("test_channel")
    
    # Start threads
    receiver_thread = threading.Thread(target=receiver_func)
    sender_thread = threading.Thread(target=sender_func)
    
    receiver_thread.start()
    sender_thread.start()
    
    receiver_thread.join()
    sender_thread.join()
    
    print("Test completed!")
