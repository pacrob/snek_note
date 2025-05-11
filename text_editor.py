import tkinter as tk
from tkinter import scrolledtext, Menu, filedialog, messagebox

class CollaborativeTextEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Collaborative Text Editor")
        self.root.geometry("800x600")
        
        # Set up the main text area with scrollbars
        self.text_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, 
                                                  font=("Courier New", 12))
        self.text_area.pack(expand=True, fill='both', padx=10, pady=10)
        
        # Track changes for real-time sync
        self.text_area.bind('<KeyRelease>', self.on_text_change)
        
        # Create the menubar
        self.create_menu()
        
        # Status bar for connection info
        self.status_var = tk.StringVar()
        self.status_var.set("Not connected")
        self.status_bar = tk.Label(self.root, textvariable=self.status_var, 
                                  bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Peer information
        self.peers = []
        
    def create_menu(self):
        menubar = Menu(self.root)
        
        # File menu
        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="New", command=self.new_file)
        file_menu.add_command(label="Open", command=self.open_file)
        file_menu.add_command(label="Save", command=self.save_file)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
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
    
    def on_text_change(self, event=None):
        """This method will be called whenever text changes"""
        # This is where we'll add p2p sync logic later
        # For now, we'll just print that a change happened
        print("Text changed, would sync here")
    
    def connect_to_peer(self):
        """Show a dialog to enter peer address and connect"""
        peer_window = tk.Toplevel(self.root)
        peer_window.title("Connect to Peer")
        peer_window.geometry("400x150")
        
        tk.Label(peer_window, text="Enter peer address:").pack(pady=10)
        
        address_entry = tk.Entry(peer_window, width=40)
        address_entry.pack(pady=10)
        
        def on_connect():
            address = address_entry.get()
            if address:
                # This is where actual connection logic will go
                self.peers.append(address)  # Just storing for now
                self.status_var.set(f"Connected to {len(self.peers)} peer(s)")
                messagebox.showinfo("Connected", f"Connected to peer: {address}")
                peer_window.destroy()
        
        tk.Button(peer_window, text="Connect", command=on_connect).pack(pady=10)
    
    def show_my_address(self):
        """Display this peer's address"""
        # This will be implemented when we add p2p functionality
        # For now, just show a placeholder
        messagebox.showinfo("My Address", "Your address will appear here when p2p is implemented")
    
    def list_peers(self):
        """Show a list of connected peers"""
        if not self.peers:
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
        for i, peer in enumerate(self.peers):
            peers_list.insert(i, peer)
        
        tk.Button(peers_window, text="Close", command=peers_window.destroy).pack(pady=10)


if __name__ == "__main__":
    root = tk.Tk()
    app = CollaborativeTextEditor(root)
    root.mainloop()