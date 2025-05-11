import tkinter as tk
from tkinter import scrolledtext, Menu, filedialog, messagebox
import asyncio
import threading
import json
import time
from typing import List, Dict, Any, Optional

# py-libp2p imports
from libp2p import new_host, TProtocol
from libp2p.peer.peerinfo import info_from_p2p_addr

# Protocol ID for our application
PROTOCOL_ID = TProtocol("/text-editor/1.0.0")

class TextChange:
    """Represents a change in the text editor"""
    def __init__(self, position: str, insert: str = "", delete: str = ""):
        self.position = position  # Format: "line.column"
        self.insert = insert      # Text to insert
        self.delete = delete      # Text to delete
        self.timestamp = time.time()
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps({
            "position": self.position,
            "insert": self.insert,
            "delete": self.delete,
            "timestamp": self.timestamp
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> 'TextChange':
        """Create from JSON string"""
        data = json.loads(json_str)
        change = cls(data["position"])
        change.insert = data["insert"]
        change.delete = data["delete"]
        change.timestamp = data["timestamp"]
        return change


class P2PNetwork:
    """Manages p2p networking for the text editor"""
    def __init__(self, on_text_change_received):
        self.host = None
        self.peer_id = None
        self.peers = {}  # addr -> peer_info
        self.streams = {}  # peer_id -> stream
        self.on_text_change_received = on_text_change_received
        self.loop = None
        self.running = False
        self.thread = None
        
        # We'll start the network in a separate method to avoid initialization issues
        # This will be called after the main UI is set up
    
    def initialize_host(self):
        """Initialize the libp2p host (non-async version)"""
        try:
            # Import the necessary modules
            from libp2p import generate_new_rsa_identity
            from libp2p.security.secio.transport import Transport as SecioTransport
            from libp2p.stream_muxer.mplex.mplex import MPLEX_PROTOCOL_ID, Mplex
            
            # Create key pair for this host
            key_pair = generate_new_rsa_identity()
            
            # Set up the security and multiplexing options
            muxer_opt = {MPLEX_PROTOCOL_ID: Mplex}
            sec_opt = {TProtocol("/secio/1.0.0"): SecioTransport}
            
            # Create the host
            self.host = new_host(
                key_pair=key_pair,
                muxer_opt=muxer_opt,
                sec_opt=sec_opt,
                peerstore_opt=None
            )
            print("Successfully created libp2p host")
            
            # Get peer ID and addresses
            self.peer_id = self.host.get_id().pretty()
            
            # Set stream handler for our protocol
            self.host.set_stream_handler(PROTOCOL_ID, self.stream_handler)
            
            # Print info
            print(f"P2P node started with ID: {self.peer_id}")
            addrs = [str(addr) for addr in self.host.get_addrs()]
            print(f"Listening on: {addrs}")
            
            # Keep reference to full address for connection
            self.full_addrs = [f"{addr}/p2p/{self.peer_id}" for addr in addrs]
            print(f"Full addresses: {self.full_addrs}")
            
            return True
        except Exception as e:
            print(f"Error initializing P2P host: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def stream_handler(self, stream):
        """Handle incoming streams (non-async version)"""
        peer_id = stream.muxed_conn.peer_id.pretty()
        print(f"New stream from: {peer_id}")
        
        # Store the stream
        self.streams[peer_id] = stream
        
        # Start a reader for this stream in the background
        asyncio.run_coroutine_threadsafe(self.read_from_stream(stream, peer_id), self.loop)
    
    async def read_from_stream(self, stream, peer_id):
        """Read data from stream (async version)"""
        retry_count = 0
        max_retries = 3
        
        while self.running:
            try:
                data = await stream.read()
                if not data:
                    print(f"No data received from {peer_id}, stream may be closed")
                    break
                
                # Reset retry counter on successful read
                retry_count = 0
                
                # Convert bytes to string
                try:
                    message = data.decode('utf-8')
                except UnicodeDecodeError as e:
                    print(f"Error decoding message from {peer_id}: {e}")
                    continue
                
                # Process the received text change
                try:
                    change = TextChange.from_json(message)
                    print(f"Received change from {peer_id}: {message}")
                    
                    # Call the callback to update UI - needs to be done in the main thread
                    # We use a simple approach here - in a real app, you'd want to use a thread-safe queue
                    self.on_text_change_received(change)
                except json.JSONDecodeError as e:
                    print(f"Invalid JSON from {peer_id}: {e}")
                except Exception as e:
                    print(f"Error processing message from {peer_id}: {e}")
            
            except Exception as e:
                print(f"Error reading from {peer_id}: {e}")
                retry_count += 1
                if retry_count >= max_retries:
                    print(f"Too many errors from {peer_id}, closing stream")
                    break
                await asyncio.sleep(1)  # Wait before retrying
        
        # Clean up when stream ends
        if peer_id in self.streams:
            del self.streams[peer_id]
            print(f"Stream from {peer_id} closed")
    
    def connect_to_peer(self, addr):
        """Connect to a peer using multiaddress (non-async version)"""
        try:
            # Parse the multiaddress to get peer info
            peer_info = info_from_p2p_addr(addr)
            
            # Connect to the peer
            self.host.connect(peer_info)
            self.peers[addr] = peer_info
            
            # Open a stream to the peer
            stream = self.host.new_stream(peer_info.peer_id, [PROTOCOL_ID])
            peer_id = peer_info.peer_id.pretty()
            self.streams[peer_id] = stream
            
            # Start a reader for this stream
            asyncio.run_coroutine_threadsafe(self.read_from_stream(stream, peer_id), self.loop)
            
            return True, f"Connected to {peer_id}"
        except Exception as e:
            print(f"Connection error: {e}")
            import traceback
            traceback.print_exc()
            return False, f"Failed to connect: {str(e)}"
    
    def broadcast_change(self, change):
        """Send text change to all connected peers (non-async version)"""
        try:
            message = change.to_json()
            data = message.encode('utf-8')
            
            # Make a copy of the streams dictionary to avoid modification during iteration
            current_streams = dict(self.streams)
            failed_peers = []
            
            for peer_id, stream in current_streams.items():
                try:
                    # Write to the stream (non-async)
                    stream.write(data)
                    print(f"Sent change to {peer_id}")
                except Exception as e:
                    print(f"Error sending to {peer_id}: {e}")
                    failed_peers.append(peer_id)
            
            # Clean up failed streams
            for peer_id in failed_peers:
                if peer_id in self.streams:
                    del self.streams[peer_id]
            
            return True
        except Exception as e:
            print(f"Error in broadcast: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def start_in_thread(self):
        """Start the network in a separate thread"""
        def run_network():
            # Create a new event loop for this thread
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Initialize the host
            self.running = self.initialize_host()
            
            if self.running:
                # Run the event loop
                try:
                    self.loop.run_forever()
                except Exception as e:
                    print(f"Error in event loop: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    self.loop.close()
        
        # Start the thread
        self.thread = threading.Thread(target=run_network, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop the network"""
        if self.running:
            self.running = False
            if self.loop:
                self.loop.call_soon_threadsafe(self.loop.stop)
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=2)
    
    def get_peer_addresses(self):
        """Get this node's addresses"""
        return self.full_addrs if hasattr(self, 'full_addrs') else []
    
    def get_connected_peers(self):
        """Get list of connected peers"""
        return list(self.streams.keys())
    
    def connect_to_peer_sync(self, addr):
        """Connect to peer (already synchronous)"""
        return self.connect_to_peer(addr)
    
    def broadcast_change_sync(self, change):
        """Broadcast change (already synchronous)"""
        return self.broadcast_change(change)


class CollaborativeTextEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Collaborative Text Editor")
        self.root.geometry("800x600")
        
        # Flag to disable event handling while applying remote changes
        self.applying_remote_change = False
        
        # Set up the main text area with scrollbars
        self.text_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, 
                                                   font=("Courier New", 12))
        self.text_area.pack(expand=True, fill='both', padx=10, pady=10)
        
        # Store previous content for change detection
        self.previous_content = self.text_area.get(1.0, tk.END)
        
        # Track changes for real-time sync
        self.text_area.bind('<KeyRelease>', self.on_text_change)
        
        # Create the menubar
        self.create_menu()
        
        # Status bar for connection info
        self.status_var = tk.StringVar()
        self.status_var.set("Starting P2P network...")
        self.status_bar = tk.Label(self.root, textvariable=self.status_var, 
                                  bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Initialize P2P network
        self.network = P2PNetwork(self.apply_remote_change)
        
        # Start the network after the UI is set up
        self.network.start_in_thread()
        
        # Update status after a short delay to allow network to start
        self.root.after(1000, self.update_status)
        
        # Set up clean shutdown
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def update_status(self):
        """Update the status bar with network info"""
        if hasattr(self.network, 'peer_id') and self.network.peer_id:
            peers = self.network.get_connected_peers()
            peer_count = len(peers)
            self.status_var.set(f"Connected to {peer_count} peer(s). My ID: {self.network.peer_id[:10]}...")
        else:
            self.status_var.set("P2P network starting...")
            # Try again after a delay
            self.root.after(1000, self.update_status)
    
    def create_menu(self):
        menubar = Menu(self.root)
        
        # File menu
        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="New", command=self.new_file)
        file_menu.add_command(label="Open", command=self.open_file)
        file_menu.add_command(label="Save", command=self.save_file)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Network menu
        network_menu = Menu(menubar, tearoff=0)
        network_menu.add_command(label="Connect to Peer", command=self.connect_to_peer)
        network_menu.add_command(label="Show My Address", command=self.show_my_address)
        network_menu.add_command(label="List Connected Peers", command=self.list_peers)
        menubar.add_cascade(label="Network", menu=network_menu)
        
        self.root.config(menu=menubar)
    
    def new_file(self):
        self.text_area.delete(1.0, tk.END)
    
    def open_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r') as file:
                    content = file.read()
                    self.text_area.delete(1.0, tk.END)
                    self.text_area.insert(tk.END, content)
            except Exception as e:
                messagebox.showerror("Error", f"Could not open file: {e}")
    
    def save_file(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            try:
                content = self.text_area.get(1.0, tk.END)
                with open(file_path, 'w') as file:
                    file.write(content)
            except Exception as e:
                messagebox.showerror("Error", f"Could not save file: {e}")
    
    def get_cursor_position(self):
        """Get current cursor position as 'line.column'"""
        return self.text_area.index(tk.INSERT)
    
    def on_text_change(self, event=None):
        """Called when text changes locally"""
        if self.applying_remote_change:
            return  # Skip if we're applying a remote change
        
        try:
            # Get current content
            current_content = self.text_area.get(1.0, tk.END)
            
            # Skip if no real change (happens with some key presses)
            if current_content == self.previous_content:
                return
                
            # Get cursor position
            position = self.get_cursor_position()
            
            # Determine what changed
            if len(current_content) > len(self.previous_content):
                # Text was inserted
                # Find what was inserted by comparing the strings
                # This is a simplification - in a real app we'd need more sophisticated diff
                inserted = ""
                for i in range(min(len(current_content), len(self.previous_content))):
                    if current_content[i] != self.previous_content[i]:
                        inserted = current_content[i:i+len(current_content)-len(self.previous_content)]
                        break
                
                change = TextChange(position=position, insert=inserted)
                print(f"Detected insert: {inserted} at {position}")
            else:
                # Text was deleted
                # Find what was deleted by comparing the strings
                # This is a simplification - in a real app we'd need more sophisticated diff
                deleted = ""
                for i in range(min(len(current_content), len(self.previous_content))):
                    if current_content[i] != self.previous_content[i]:
                        deleted = self.previous_content[i:i+len(self.previous_content)-len(current_content)]
                        break
                
                change = TextChange(position=position, delete=deleted)
                print(f"Detected delete: {deleted} at {position}")
            
            # Update previous content
            self.previous_content = current_content
            
            # Broadcast the change
            if change.insert or change.delete:
                print(f"Broadcasting change: {change.to_json()}")
                self.network.broadcast_change_sync(change)
                
        except Exception as e:
            print(f"Error handling text change: {e}")
            import traceback
            traceback.print_exc()
    
    def apply_remote_change(self, change: TextChange):
        """Apply a change received from a peer"""
        # Set flag to avoid re-broadcasting
        self.applying_remote_change = True
        
        try:
            # Apply the change to our text
            if change.insert:
                # Insert the text at the specified position
                self.text_area.insert(change.position, change.insert)
                print(f"Applied insert: '{change.insert}' at {change.position}")
                
                # Move cursor to the end of the inserted text
                new_pos = self.text_area.index(f"{change.position}+{len(change.insert)}c")
                self.text_area.mark_set(tk.INSERT, new_pos)
                
            elif change.delete:
                # If we know what was deleted, we can verify before deleting
                pos = change.position
                
                # If the delete string is specified, delete that many characters
                delete_length = len(change.delete)
                if delete_length > 0:
                    # Check if the text at position matches what should be deleted
                    text_to_check = self.text_area.get(pos, f"{pos}+{delete_length}c")
                    
                    if text_to_check == change.delete:
                        # Delete the exact text
                        self.text_area.delete(pos, f"{pos}+{delete_length}c")
                        print(f"Applied delete: '{change.delete}' at {change.position}")
                    else:
                        print(f"Warning: Text to delete '{change.delete}' doesn't match '{text_to_check}' at position {pos}")
                        # Fall back to deleting one character
                        self.text_area.delete(pos, f"{pos}+1c")
                else:
                    # If no specific delete text, delete one character
                    self.text_area.delete(pos, f"{pos}+1c")
                    print(f"Applied delete: 1 character at {change.position}")
                
                # Move cursor to the position after deletion
                self.text_area.mark_set(tk.INSERT, pos)
            
            # Update previous content after applying the change
            self.previous_content = self.text_area.get(1.0, tk.END)
            
        except Exception as e:
            print(f"Error applying remote change: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Reset flag
            self.applying_remote_change = False
    
    def connect_to_peer(self):
        """Show dialog to enter peer address and connect"""
        peer_window = tk.Toplevel(self.root)
        peer_window.title("Connect to Peer")
        peer_window.geometry("600x150")
        
        tk.Label(peer_window, text="Enter peer multiaddress:").pack(pady=10)
        
        address_entry = tk.Entry(peer_window, width=60)
        address_entry.pack(pady=10)
        
        def on_connect():
            address = address_entry.get()
            if address:
                try:
                    success, message = self.network.connect_to_peer_sync(address)
                    if success:
                        messagebox.showinfo("Connected", message)
                        self.update_status()
                    else:
                        messagebox.showerror("Connection Failed", message)
                except Exception as e:
                    messagebox.showerror("Error", f"Connection error: {str(e)}")
                finally:
                    peer_window.destroy()
        
        tk.Button(peer_window, text="Connect", command=on_connect).pack(pady=10)
    
    def show_my_address(self):
        """Display this peer's address"""
        addresses = self.network.get_peer_addresses()
        if not addresses:
            messagebox.showinfo("My Address", "Network not yet initialized. Try again in a moment.")
            return
            
        addr_window = tk.Toplevel(self.root)
        addr_window.title("My Addresses")
        addr_window.geometry("700x300")
        
        tk.Label(addr_window, text="Your peer addresses (share these with others to connect):").pack(pady=10)
        
        # Create a listbox with scrollbar
        frame = tk.Frame(addr_window)
        scrollbar = tk.Scrollbar(frame)
        addr_list = tk.Listbox(frame, width=80, height=10, yscrollcommand=scrollbar.set)
        
        scrollbar.config(command=addr_list.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        addr_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        frame.pack(pady=10)
        
        # Populate the list
        for i, addr in enumerate(addresses):
            addr_list.insert(i, addr)
        
        # Copy button
        def copy_address():
            selected = addr_list.curselection()
            if selected:
                addr = addr_list.get(selected[0])
                self.root.clipboard_clear()
                self.root.clipboard_append(addr)
                messagebox.showinfo("Copied", "Address copied to clipboard")
        
        tk.Button(addr_window, text="Copy Selected", command=copy_address).pack(pady=5)
        tk.Button(addr_window, text="Close", command=addr_window.destroy).pack(pady=5)
    
    def list_peers(self):
        """Show a list of connected peers"""
        peers = self.network.get_connected_peers()
        if not peers:
            messagebox.showinfo("Peers", "No peers connected")
            return
            
        peers_window = tk.Toplevel(self.root)
        peers_window.title("Connected Peers")
        peers_window.geometry("400x300")
        
        tk.Label(peers_window, text="Connected Peers:").pack(pady=10)
        
        # Create a listbox with scrollbar
        frame = tk.Frame(peers_window)
        scrollbar = tk.Scrollbar(frame)
        peers_list = tk.Listbox(frame, width=50, height=10, yscrollcommand=scrollbar.set)
        
        scrollbar.config(command=peers_list.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        peers_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        frame.pack(pady=10)
        
        # Populate the list
        for i, peer in enumerate(peers):
            peers_list.insert(i, peer)
        
        tk.Button(peers_window, text="Close", command=peers_window.destroy).pack(pady=10)
    
    def on_close(self):
        """Clean up when closing the application"""
        try:
            # Stop the network
            if hasattr(self, 'network'):
                self.network.stop()
        finally:
            # Destroy the window
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = CollaborativeTextEditor(root)
    root.mainloop()