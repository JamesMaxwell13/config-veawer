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

  function sendCommand() {
    const command = input.value;
    if (!command.trim() || !socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    socket.send(JSON.stringify({ type: "input", data: `${command}\n` }));
    input.value = "";
    input.focus();
  }

  function connect() {
    socket = new WebSocket(websocketUrl(root.dataset.wsPath));
    setStatus("Подключение", "text-secondary");

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
          setStatus("Подключено", "text-success");
          input.disabled = false;
          sendButton.disabled = false;
          input.focus();
        } else if (message.state === "connecting") {
          setStatus("Подключение", "text-secondary");
        }
      } else if (message.type === "error") {
        appendOutput(`\n[ERROR] ${message.message}\n`);
        setStatus("Ошибка", "text-danger");
      }
    });

    socket.addEventListener("close", () => {
      if (!connected && !disconnectRequested) {
        setStatus("Невозможно подключиться", "text-danger");
      } else {
        setStatus("Отключено", "text-secondary");
      }
      input.disabled = true;
      sendButton.disabled = true;
      if (disconnectRequested && root.dataset.deviceUrl) {
        window.location.href = root.dataset.deviceUrl;
      }
    });

    socket.addEventListener("error", () => {
      appendOutput("\n[ERROR] Ошибка WebSocket-соединения\n");
      setStatus("Невозможно подключиться", "text-danger");
    });
  }

  input.disabled = true;
  sendButton.disabled = true;

  sendButton.addEventListener("click", sendCommand);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendCommand();
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
