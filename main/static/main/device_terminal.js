(function () {
  const root = document.getElementById("device-terminal");
  if (!root) {
    return;
  }

  const output = document.getElementById("terminal-output");
  const input = document.getElementById("terminal-input");
  const sendButton = document.getElementById("terminal-send");
  const disconnectButton = document.getElementById("terminal-disconnect");
  const statusBadge = document.getElementById("terminal-status");

  let socket = null;
  let disconnectRequested = false;
  let connected = false;
  const commandHistory = [];
  const maxHistorySize = 100;
  let historyIndex = null;
  let historyDraft = "";

  function websocketUrl(path) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}${path}`;
  }

  function appendOutput(text) {
    output.textContent += text;
    output.scrollTop = output.scrollHeight;
  }

  function setStatus(label, className) {
    statusBadge.textContent = label;
    statusBadge.className = `terminal-status ${className}`;
  }

  function rememberCommand(command) {
    if (commandHistory[commandHistory.length - 1] !== command) {
      commandHistory.push(command);
      if (commandHistory.length > maxHistorySize) {
        commandHistory.shift();
      }
    }
    historyIndex = null;
    historyDraft = "";
  }

  function setInputValue(value) {
    input.value = value;
    input.setSelectionRange(input.value.length, input.value.length);
  }

  function showPreviousCommand() {
    if (!commandHistory.length) {
      return;
    }
    if (historyIndex === null) {
      historyDraft = input.value;
      historyIndex = commandHistory.length - 1;
    } else if (historyIndex > 0) {
      historyIndex -= 1;
    }
    setInputValue(commandHistory[historyIndex]);
  }

  function showNextCommand() {
    if (historyIndex === null) {
      return;
    }
    if (historyIndex < commandHistory.length - 1) {
      historyIndex += 1;
      setInputValue(commandHistory[historyIndex]);
      return;
    }
    historyIndex = null;
    setInputValue(historyDraft);
    historyDraft = "";
  }

  function sendCommand() {
    const command = input.value;
    const trimmedCommand = command.trim();
    if (!trimmedCommand || !socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    socket.send(JSON.stringify({ type: "input", data: `${command}\n` }));
    rememberCommand(trimmedCommand);
    input.value = "";
    input.focus();
  }

  function connect() {
    socket = new WebSocket(websocketUrl(root.dataset.wsPath));
    setStatus("Connecting", "text-secondary");

    socket.addEventListener("open", () => {
      setStatus("SSH", "text-info");
    });

    socket.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch (error) {
        appendOutput(event.data);
        return;
      }

      if (message.type === "output") {
        appendOutput(message.data || "");
      } else if (message.type === "status") {
        if (message.state === "connected") {
          connected = true;
          setStatus("Connected", "text-success");
          input.disabled = false;
          sendButton.disabled = false;
          input.focus();
        } else if (message.state === "connecting") {
          setStatus("Connecting", "text-secondary");
        }
      } else if (message.type === "error") {
        appendOutput(`\n[ERROR] ${message.message}\n`);
        setStatus("Error", "text-danger");
      }
    });

    socket.addEventListener("close", () => {
      if (!connected && !disconnectRequested) {
        setStatus("Connection failed", "text-danger");
      } else {
        setStatus("Disconnected", "text-secondary");
      }
      input.disabled = true;
      sendButton.disabled = true;
      if (disconnectRequested && root.dataset.deviceUrl) {
        window.location.href = root.dataset.deviceUrl;
      }
    });

    socket.addEventListener("error", () => {
      appendOutput("\n[ERROR] WebSocket connection error\n");
      setStatus("Connection failed", "text-danger");
    });
  }

  input.disabled = true;
  sendButton.disabled = true;

  sendButton.addEventListener("click", sendCommand);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendCommand();
    } else if (event.key === "ArrowUp" && !event.shiftKey) {
      event.preventDefault();
      showPreviousCommand();
    } else if (event.key === "ArrowDown" && !event.shiftKey) {
      event.preventDefault();
      showNextCommand();
    }
  });
  disconnectButton.addEventListener("click", () => {
    disconnectRequested = true;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "disconnect" }));
      socket.close();
    } else if (socket && socket.readyState === WebSocket.CONNECTING) {
      socket.close();
    } else if (root.dataset.deviceUrl) {
      window.location.href = root.dataset.deviceUrl;
    }
  });

  connect();
})();
