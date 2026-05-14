(function () {
  const KEY_GROUPS = [
    {
      className: "yaml-key-interface",
      pattern: /^(interfaces?|interface|ports?|port|name|description|mode|vlan|vlans|ip|mask|gateway|shutdown)$/i,
    },
    {
      className: "yaml-key-command",
      pattern: /^(commands?|command|raw_commands?|operation|operation_type|template|command_body|device_task|task|tasks?)$/i,
    },
    {
      className: "yaml-key-argument",
      pattern: /^(args?|arguments?|params?|parameters?|value|values|source|version|version_name|config|config_checksum|commit_hash|redacted)$/i,
    },
  ];

  const escapeHtml = (value) => value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  const span = (className, value) => `<span class="${className}">${escapeHtml(value)}</span>`;

  function splitComment(value) {
    let quote = null;
    for (let i = 0; i < value.length; i += 1) {
      const char = value[i];
      const prev = value[i - 1];
      if ((char === '"' || char === "'") && prev !== "\\") {
        quote = quote === char ? null : (quote || char);
      }
      if (char === "#" && !quote && (i === 0 || /\s/.test(value[i - 1]))) {
        return [value.slice(0, i), value.slice(i)];
      }
    }
    return [value, ""];
  }

  function keyClass(key) {
    const normalized = key.replace(/^["']|["']$/g, "");
    const group = KEY_GROUPS.find((entry) => entry.pattern.test(normalized));
    return group ? group.className : "yaml-key";
  }

  function highlightValue(rawValue) {
    if (!rawValue) {
      return "";
    }

    const leading = rawValue.match(/^\s*/)[0];
    const trailing = rawValue.match(/\s*$/)[0];
    const value = rawValue.slice(leading.length, rawValue.length - trailing.length);

    if (!value) {
      return escapeHtml(rawValue);
    }

    let className = "yaml-string";
    if (/^(true|false|yes|no|on|off)$/i.test(value)) {
      className = "yaml-bool";
    } else if (/^(null|~)$/i.test(value)) {
      className = "yaml-null";
    } else if (/^[+-]?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value)) {
      className = "yaml-number";
    } else if (/^[&][\w.-]+$/.test(value)) {
      className = "yaml-anchor";
    } else if (/^[*][\w.-]+$/.test(value)) {
      className = "yaml-alias";
    } else if (/^![\w!:/.-]+$/.test(value)) {
      className = "yaml-tag";
    } else if (/^[>|]-?$/.test(value)) {
      className = "yaml-punctuation";
    } else if (/^[{}\[\],]$/.test(value)) {
      className = "yaml-punctuation";
    }

    return `${escapeHtml(leading)}${span(className, value)}${escapeHtml(trailing)}`;
  }

  function highlightLine(line) {
    const [content, comment] = splitComment(line);
    const indent = content.match(/^\s*/)[0];
    let rest = content.slice(indent.length);
    let html = span("yaml-indent", indent);

    const listMatch = rest.match(/^(-\s*)/);
    if (listMatch) {
      html += span("yaml-marker", listMatch[1]);
      rest = rest.slice(listMatch[1].length);
    }

    const keyMatch = rest.match(/^((?:"[^"]+"|'[^']+'|[A-Za-z0-9_.\/-]+)(?:\s+[^:#]+)?)(\s*):(\s*)/);
    if (keyMatch) {
      html += span(keyClass(keyMatch[1].trim()), keyMatch[1]);
      html += escapeHtml(keyMatch[2]);
      html += span("yaml-punctuation", ":");
      html += escapeHtml(keyMatch[3]);
      rest = rest.slice(keyMatch[0].length);
    }

    html += highlightValue(rest);
    if (comment) {
      html += span("yaml-comment", comment);
    }
    return html || "\n";
  }

  function highlightYaml(source) {
    return source.split("\n").map(highlightLine).join("\n");
  }

  function highlightCodeBlock(code) {
    if (code.dataset.yamlHighlighted === "true") {
      return;
    }
    code.innerHTML = highlightYaml(code.textContent);
    code.dataset.yamlHighlighted = "true";
  }

  function highlightDiffLine(line) {
    if (/^(---|\+\+\+|@@)/.test(line)) {
      return span("yaml-diff-line yaml-diff-meta", line);
    }
    if (/^[+-]/.test(line)) {
      const className = line[0] === "+" ? "yaml-diff-add" : "yaml-diff-remove";
      return span(`yaml-diff-line ${className}`, line);
    }
    return span("yaml-diff-line", line);
  }

  function highlightDiffBlock(code) {
    if (code.dataset.yamlHighlighted === "true") {
      return;
    }
    const lines = code.textContent.split("\n");
    while (lines.length > 0 && lines[lines.length - 1] === "") {
      lines.pop();
    }
    code.innerHTML = lines.map(highlightDiffLine).join("");
    code.dataset.yamlHighlighted = "true";
  }

  function buildEditor(textarea) {
    if (textarea.dataset.yamlEditorReady === "true") {
      return;
    }

    const wrapper = document.createElement("div");
    wrapper.className = "cw-yaml-editor";
    wrapper.style.minHeight = `${Math.max(textarea.offsetHeight || 0, 192)}px`;

    const highlight = document.createElement("pre");
    highlight.className = "cw-yaml-editor__highlight cw-yaml-highlight";
    const code = document.createElement("code");
    highlight.append(code);

    textarea.parentNode.insertBefore(wrapper, textarea);
    wrapper.append(highlight, textarea);

    const sync = () => {
      code.innerHTML = highlightYaml(`${textarea.value}\n`);
      highlight.scrollTop = textarea.scrollTop;
      highlight.scrollLeft = textarea.scrollLeft;
    };

    textarea.addEventListener("input", sync);
    textarea.addEventListener("scroll", sync);
    textarea.addEventListener("keydown", (event) => {
      if (event.key !== "Tab") {
        return;
      }
      event.preventDefault();
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      textarea.setRangeText("  ", start, end, "end");
      sync();
    });

    textarea.dataset.yamlEditorReady = "true";
    sync();
  }

  function initYamlHighlighting(root) {
    root.querySelectorAll("code[data-yaml-highlight], code.language-yaml, code.language-yml")
      .forEach(highlightCodeBlock);
    root.querySelectorAll("code[data-yaml-diff]")
      .forEach(highlightDiffBlock);
    root.querySelectorAll("textarea[data-yaml-editor], textarea.yaml-editor")
      .forEach(buildEditor);
  }

  document.addEventListener("DOMContentLoaded", () => initYamlHighlighting(document));
  document.body?.addEventListener("htmx:afterSwap", (event) => initYamlHighlighting(event.target));
})();
