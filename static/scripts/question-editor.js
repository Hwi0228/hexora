const configNode = document.getElementById("question-editor-config");
const editorConfig = configNode
  ? JSON.parse(configNode.textContent || "{}")
  : {};

    const form = document.getElementById("question-form");
    const sources = Array.from(document.querySelectorAll("[data-source]"));
    const editors = new Map();
    sources.forEach((source) => {
      source.dataset.originalRequired = source.hasAttribute("required") ? "true" : "false";
    });

    try {
      if (!window.Quill) throw new Error("Quill 2 CDN script did not load.");
      const Delta = Quill.import("delta");
      const InlineEmbed = Quill.import("blots/embed");
      const BlockEmbed = Quill.import("blots/block/embed");
      function renderMath(node, value, displayMode) {
        const equation = value && typeof value === "object"
          ? value
          : { latex: String(value || ""), inputFormat: "latex", inputSource: String(value || "") };
        const latex = String(equation.latex || "");
        node.dataset.latex = latex;
        node.dataset.inputFormat = equation.inputFormat === "hancom" ? "hancom" : "latex";
        node.dataset.inputSource = String(equation.inputSource || latex);
        node.dataset.mathObject = displayMode ? "block" : "inline";
        node.setAttribute("contenteditable", "false");
        node.setAttribute("aria-label", displayMode ? "블록 수식" : "인라인 수식");
        if (window.katex) {
          window.katex.render(latex, node, { throwOnError: false, displayMode });
        } else {
          node.textContent = latex;
        }
      }

      class InlineMathBlot extends InlineEmbed {
        static blotName = "inlineMath";
        static tagName = "span";
        static className = "ql-math-inline";
        static create(value) {
          const node = super.create();
          renderMath(node, value, false);
          return node;
        }
        static value(node) {
          return {
            latex: node.dataset.latex || "",
            inputFormat: node.dataset.inputFormat || "latex",
            inputSource: node.dataset.inputSource || node.dataset.latex || ""
          };
        }
      }

      class BlockMathBlot extends BlockEmbed {
        static blotName = "blockMath";
        static tagName = "div";
        static className = "ql-math-block";
        static create(value) {
          const node = super.create();
          renderMath(node, value, true);
          return node;
        }
        static value(node) {
          return {
            latex: node.dataset.latex || "",
            inputFormat: node.dataset.inputFormat || "latex",
            inputSource: node.dataset.inputSource || node.dataset.latex || ""
          };
        }
      }

      Quill.register(InlineMathBlot, true);
      Quill.register(BlockMathBlot, true);


      const mathDialog = document.getElementById("math-input-dialog");
      const mathDialogForm = document.getElementById("math-input-form");
      const mathInput = document.getElementById("math-latex-input");
      const hancomInput = document.getElementById("math-hancom-input");
      const mathInputMode = document.getElementById("math-input-format");
      const latexMathFields = document.getElementById("latex-math-fields");
      const hancomMathFields = document.getElementById("hancom-math-fields");
      const conversionError = document.getElementById("math-conversion-error");
      const mathCancel = document.getElementById("math-input-cancel");
      let mathDialogAction = null;

      function closeMathDialog() {
        mathDialog.hidden = true;
        mathDialogAction = null;
      }

      function openMathDialog(initialValue, action) {
        const equation = initialValue && typeof initialValue === "object"
          ? initialValue
          : { latex: String(initialValue || ""), inputFormat: "latex", inputSource: String(initialValue || "") };
        mathInputMode.value = equation.inputFormat === "hancom" ? "hancom" : "latex";
        mathInput.value = equation.inputFormat === "hancom"
          ? equation.latex || ""
          : equation.inputSource || equation.latex || "";
        hancomInput.value = equation.inputFormat === "hancom"
          ? equation.inputSource || equation.latex || ""
          : "";
        updateMathInputFields();
        conversionError.hidden = true;
        mathDialogAction = action;
        mathDialog.hidden = false;
        requestAnimationFrame(() => {
          mathInput.focus();
          mathInput.select();
        });
      }

      function updateMathInputFields() {
        const hancomMode = mathInputMode.value === "hancom";
        latexMathFields.hidden = hancomMode;
        hancomMathFields.hidden = !hancomMode;
      }

      mathInputMode.addEventListener("change", () => {
        updateMathInputFields();
        conversionError.hidden = true;
        (mathInputMode.value === "hancom" ? hancomInput : mathInput).focus();
      });

      mathDialogForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const inputFormat = mathInputMode.value;
        const source = (inputFormat === "hancom" ? hancomInput : mathInput).value.trim();
        const activeInput = inputFormat === "hancom" ? hancomInput : mathInput;
        activeInput.setCustomValidity("");
        if (!source) {
          activeInput.setCustomValidity(inputFormat === "hancom"
            ? "한컴 수식 스크립트를 입력해 주세요."
            : "LaTeX 수식을 입력해 주세요.");
          activeInput.reportValidity();
          return;
        }
        let latex = source;
        if (inputFormat === "hancom") {
          conversionError.hidden = true;
          try {
            latex = window.EasyConvertEquation.hwpEquationToLaTeX(source);
          } catch (error) {
            const invalidRootOrder = /^sqrt\s*\{[^}]+\}\s+of\b/i.test(source);
            conversionError.textContent = invalidRootOrder
              ? "'sqrt {3} of {5}' 형식은 사용할 수 없습니다. 다섯제곱근을 뜻한다면 'root 5 of {3}'처럼 입력해 주세요."
              : (error.message || "수식 문법을 확인해 주세요.");
            conversionError.hidden = false;
            hancomInput.focus();
            return;
          }
        }
        if (!latex) {
          mathInput.setCustomValidity("LaTeX 수식을 입력해 주세요.");
          mathInput.reportValidity();
          return;
        }
        const action = mathDialogAction;
        closeMathDialog();
        if (action) action({ latex, inputFormat, inputSource: source });
      });
      mathInput.addEventListener("input", () => mathInput.setCustomValidity(""));
      hancomInput.addEventListener("input", () => hancomInput.setCustomValidity(""));
      mathCancel.addEventListener("click", closeMathDialog);

      const imageDialog = document.getElementById("image-input-dialog");
      const imageDialogForm = document.getElementById("image-input-form");
      const imageFileInput = document.getElementById("image-file-input");
      const imageCancel = document.getElementById("image-input-cancel");
      let imageDialogAction = null;

      function closeImageDialog() {
        imageDialog.hidden = true;
        imageDialogAction = null;
        imageFileInput.value = "";
      }

      function openImageDialog(action) {
        imageDialogAction = action;
        imageDialog.hidden = false;
        imageFileInput.focus();
      }

      imageCancel.addEventListener("click", closeImageDialog);
      imageDialog.addEventListener("click", (event) => {
        if (event.target === imageDialog) closeImageDialog();
      });
      imageDialogForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const file = imageFileInput.files && imageFileInput.files[0];
        if (!file) {
          imageFileInput.setCustomValidity("삽입할 이미지 파일을 선택해 주세요.");
          imageFileInput.reportValidity();
          return;
        }
        imageFileInput.setCustomValidity("");
        if (!/^image\/(?:png|jpeg|webp|gif)$/i.test(file.type) || file.size > 8 * 1024 * 1024) {
          window.alert("PNG, JPEG, WebP, GIF 이미지 중 8MB 이하 파일만 삽입할 수 있습니다.");
          return;
        }

        const reader = new FileReader();
        reader.onerror = () => window.alert("이미지 파일을 읽지 못했습니다.");
        reader.onload = () => {
          const image = new Image();
          image.onerror = () => window.alert("이미지 파일을 해석하지 못했습니다.");
          image.onload = () => {
            const maxSide = 1600;
            const scale = Math.min(1, maxSide / Math.max(image.naturalWidth, image.naturalHeight));
            const canvas = document.createElement("canvas");
            canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
            canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
            const context = canvas.getContext("2d");
            if (!context) {
              window.alert("이미지 변환을 지원하지 않는 브라우저입니다.");
              return;
            }
            context.drawImage(image, 0, 0, canvas.width, canvas.height);
            let dataUrl = canvas.toDataURL("image/webp", 0.78);
            if (!dataUrl.startsWith("data:image/webp;")) {
              dataUrl = canvas.toDataURL("image/jpeg", 0.78);
            }
            if (dataUrl.length > 1350000) {
              dataUrl = canvas.toDataURL("image/jpeg", 0.62);
            }
            if (dataUrl.length > 1400000) {
              window.alert("압축 후에도 이미지가 너무 큽니다. 해상도가 낮은 이미지로 다시 시도해 주세요.");
              return;
            }
            const action = imageDialogAction;
            closeImageDialog();
            if (action) action(dataUrl);
          };
          image.src = String(reader.result || "");
        };
        reader.readAsDataURL(file);
      });
      mathDialog.addEventListener("click", (event) => {
        if (event.target === mathDialog) closeMathDialog();
      });
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !mathDialog.hidden) closeMathDialog();
      });

      function insertImage() {
        const quill = this.quill;
        const range = quill.getSelection(true) || {
          index: Math.max(0, quill.getLength() - 1), length: 0
        };
        openImageDialog((dataUrl) => {
          quill.focus();
          if (range.length) quill.deleteText(range.index, range.length, "user");
          quill.insertEmbed(range.index, "image", dataUrl, "user");
          quill.setSelection(range.index + 1, 0, "silent");
        });
      }

      function insertTable() {
        const table = this.quill.getModule("table");
        if (!table || typeof table.insertTable !== "function") {
          window.alert("표 편집 모듈을 불러오지 못했습니다.");
          return;
        }
        table.insertTable(2, 2);
      }

      function insertMath(format) {
        const quill = this.quill;
        const range = quill.getSelection(true) || {
          index: Math.max(0, quill.getLength() - 1), length: 0
        };
        openMathDialog("", (equation) => {
          quill.focus();
          if (range.length) quill.deleteText(range.index, range.length, "user");
          const index = range.index;
          quill.insertEmbed(index, format, equation, "user");
          quill.setSelection(index + 1, 0, "silent");
        });
      }

      // Serialize the editor's source HTML, never KaTeX's rendered SVG.
      // Quill embeds keep the original TeX in data-latex; their inner DOM is
      // presentation-only and contains SVG path commands that must not be saved.
      function serializeEditorNode(node) {
        const clone = node.cloneNode(true);
        clone.querySelectorAll(".ql-math-inline, .ql-math-block").forEach((mathNode) => {
          const displayMode = mathNode.classList.contains("ql-math-block");
          const cleanNode = document.createElement(displayMode ? "div" : "span");
          cleanNode.className = displayMode ? "ql-math-block" : "ql-math-inline";
          cleanNode.setAttribute("data-latex", mathNode.dataset.latex || "");
          cleanNode.setAttribute("data-input-format", mathNode.dataset.inputFormat || "latex");
          cleanNode.setAttribute("data-input-source", mathNode.dataset.inputSource || mathNode.dataset.latex || "");
          cleanNode.setAttribute("data-math-object", displayMode ? "block" : "inline");
          cleanNode.setAttribute("aria-label", displayMode ? "블록 수식" : "인라인 수식");
          mathNode.replaceWith(cleanNode);
        });
        return clone.outerHTML;
      }

      function serializeChoices(quill) {
        return Array.from(quill.root.children)
          .filter((node) => node.textContent.trim() ||
            node.querySelector(".ql-math-inline, .ql-math-block"))
          .map(serializeEditorNode).join("\n");
      }

      function serializeEditor(quill) {
        return Array.from(quill.root.children).map(serializeEditorNode).join("");
      }

      sources.forEach((source) => {
        const key = source.dataset.source;
        const mount = document.querySelector('[data-editor="' + key + '"]');
        const toolbar = document.querySelector('[data-toolbar="' + key + '"]');
        if (!mount || !toolbar) throw new Error("Missing editor mount or toolbar: " + key);

        // Keep Quill's current range when a formatting button receives the mouse.
        // Without this, the editor can blur before the toolbar click is processed,
        // leaving the toolbar to act on a stale or collapsed selection.
        toolbar.addEventListener("mousedown", (event) => {
          if (event.target.closest("button")) event.preventDefault();
        });

        const quill = new Quill(mount, {
          theme: "snow",
          placeholder: "내용을 입력하세요.",
          modules: {
            toolbar: {
              container: toolbar,
              handlers: {
                inlineMath: function () { insertMath.call(this, "inlineMath"); },
                blockMath: function () { insertMath.call(this, "blockMath"); },
                image: function () { insertImage.call(this); },
                insertTable: insertTable
              }
            },
            table: true,
            history: { delay: 1000, maxStack: 100, userOnly: true }
          }
        });

        // Establish a normal-weight baseline independent of the parent form label.
        quill.root.style.fontWeight = "400";

        function legacyMathEmbed(node, displayMode) {
          const latex = node.getAttribute("data-latex") ||
            node.getAttribute("data-tex") || node.textContent || "";
          const equation = {
            latex: latex.trim(),
            inputFormat: node.getAttribute("data-input-format") === "hancom" ? "hancom" : "latex",
            inputSource: node.getAttribute("data-input-source") || latex.trim()
          };
          return new Delta().insert(displayMode
            ? { blockMath: equation }
            : { inlineMath: equation }).concat(
              displayMode ? new Delta().insert("\\n") : new Delta()
            );
        }

        // Preserve math as a single object when copying/pasting within Quill.
        quill.clipboard.addMatcher("span.ql-math-inline", (node) =>
          legacyMathEmbed(node, false));
        quill.clipboard.addMatcher("div.ql-math-block", (node) =>
          legacyMathEmbed(node, true));

        // Migrate previously stored TipTap math nodes into native Quill math objects.
        quill.clipboard.addMatcher('span[data-type="inline-math"]', (node) =>
          legacyMathEmbed(node, false));
        quill.clipboard.addMatcher('div[data-type="block-math"]', (node) =>
          legacyMathEmbed(node, true));
        const initialHtml = source.value.trim();
        if (initialHtml) quill.setContents(quill.clipboard.convert({ html: initialHtml }), "silent");
        quill.on("text-change", () => {
          source.value = key === "choices"
            ? serializeChoices(quill)
            : serializeEditor(quill);
        });

        mount.addEventListener("dblclick", (event) => {
          const mathNode = event.target.closest(".ql-math-inline, .ql-math-block");
          if (!mathNode || !mount.contains(mathNode)) return;
          const blot = Quill.find(mathNode);
          if (!blot) return;
          const index = quill.getIndex(blot);
          const format = mathNode.classList.contains("ql-math-block") ? "blockMath" : "inlineMath";
          openMathDialog({
            latex: mathNode.dataset.latex || "",
            inputFormat: mathNode.dataset.inputFormat || "latex",
            inputSource: mathNode.dataset.inputSource || mathNode.dataset.latex || ""
          }, (nextEquation) => {
            quill.focus();
            quill.deleteText(index, 1, "user");
            quill.insertEmbed(index, format, nextEquation, "user");
            quill.setSelection(index + 1, 0, "silent");
          });
        });

        editors.set(key, quill);
      });

      sources.forEach((source) => { source.required = false; });
      document.documentElement.classList.add("js-editor-ready");
      form.addEventListener("submit", (event) => {
        sources.forEach((source) => {
          const editor = editors.get(source.dataset.source);
          if (editor) source.value = source.dataset.source === "choices"
            ? serializeChoices(editor)
            : serializeEditor(editor);
        });
        if (event.submitter && event.submitter.value === "draft") return;
        const missing = ["prompt", "answer"].find((key) => {
          const editor = editors.get(key);
          return editor && !editor.getText().trim() &&
            !editor.root.querySelector(".ql-math-inline, .ql-math-block");
        });
        if (missing) {
          event.preventDefault();
          window.alert(missing === "prompt" ? "문제 내용을 입력해 주세요." : "정답을 입력해 주세요.");
          editors.get(missing).focus();
        }
      });
    } catch (error) {
      console.error("Quill WYSIWYG editor unavailable; using text fallback.", error);
      document.documentElement.classList.remove("js-editor-ready");
      document.querySelectorAll(".rich-editor, .rich-toolbar").forEach((element) => {
        element.hidden = true;
      });
      sources.forEach((source) => {
        source.required = source.dataset.originalRequired === "true";
      });
    }

        const curriculum = document.getElementById("curriculum-select");
    const course = document.getElementById("course-select");
    const standards = document.getElementById("achievement-standard");
    const standardOptions = document.getElementById("achievement-standard-options");
    const standardStatus = document.getElementById("standard-status");
    const standardAreaField = document.getElementById("standard-area-field");
    const standardArea = document.getElementById("standard-area-select");
    const gradeSelect = form.querySelector('[name="grade"]');
    const selectedCourse = editorConfig.selectedCourse || "";
    let preferredCourse = selectedCourse;
    let standardsRequestId = 0;
    const subjectSelect = form.querySelector('[name="subject"]');
    const subjectCourseOptions = editorConfig.subjectCourseOptions || {};
    const storedStandard = editorConfig.storedStandard || "";
    // Older drafts may contain multiple lines; keep the first value when opening them.
    const selectedStandard = {
      value: String(storedStandard || "")
        .split(/\r?\n/)
        .map((value) => value.trim())
        .find(Boolean) || ""
    };
    const is2022Curriculum = () => curriculum.value === "2022 개정 교육과정";

    function setSelectOptions(select, values, placeholder, preferredValue) {
      const previous = preferredValue || select.value;
      select.innerHTML = "";
      const first = document.createElement("option");
      first.value = "";
      first.textContent = placeholder;
      select.appendChild(first);
      (values || []).forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      });
      if ((values || []).includes(previous)) select.value = previous;
    }

    function syncSelectedStandards() {
      standards.value = selectedStandard.value;
      standardStatus.textContent = selectedStandard.value
        ? "성취기준 1개 선택됨"
        : "적용할 성취기준을 선택하세요.";
    }

    function clearSelectedStandards() {
      selectedStandard.value = "";
      standards.value = "";
      renderStandards([]);
    }

    function renderStandards(items) {
      standardOptions.replaceChildren();
      if (!items || !items.length) {
        const empty = document.createElement("p");
        empty.className = "standard-empty";
        empty.textContent = course.value
          ? "선택한 조건에 해당하는 성취기준이 없습니다."
          : "과목과 학년을 선택하면 성취기준 목록이 표시됩니다.";
        standardOptions.appendChild(empty);
        syncSelectedStandards();
        return;
      }

      items.forEach((standard) => {
        const label = document.createElement("label");
        label.className = "standard-option";

        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "achievement-standard-choice";
        radio.value = standard;
        radio.checked = selectedStandard.value === standard;
        radio.addEventListener("change", () => {
          if (radio.checked) {
            selectedStandard.value = standard;
            syncSelectedStandards();
          }
        });

        const content = document.createElement("span");
        content.className = "standard-option-content";
        const match = standard.match(/^(\[[^\]]+\])\s*(.*)$/s);
        if (match) {
          const code = document.createElement("span");
          code.className = "standard-code";
          code.textContent = match[1];
          content.appendChild(code);
          if (match[2]) {
            content.appendChild(document.createTextNode(" " + match[2]));
          }
        } else {
          content.textContent = standard;
        }

        label.append(radio, content);
        standardOptions.appendChild(label);
      });
      syncSelectedStandards();
    }

    function rebuildCourses() {
      const options = subjectCourseOptions[subjectSelect.value] || [];
      const previous = course.value || preferredCourse;
      setSelectOptions(course, options, "교과 선택", previous);
    }

    async function loadStandards() {
      const use2022 = is2022Curriculum();
      const requestId = ++standardsRequestId;
      standardAreaField.hidden = !use2022;

      if (!course.value && !use2022) {
        renderStandards([]);
        standardStatus.textContent = "교과를 선택하면 성취기준 목록이 표시됩니다.";
        return;
      }
      standardStatus.textContent = "성취기준 목록을 불러오는 중입니다.";

      const params = new URLSearchParams({
        curriculum: curriculum.value,
        course: course.value,
        subject: subjectSelect.value,
        grade: gradeSelect.value,
        area: use2022 ? standardArea.value : ""
      });
      try {
        const response = await fetch(editorConfig.curriculumStandardsUrl + "?" + params.toString(), {
          headers: { "Accept": "application/json" }
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "성취기준을 불러오지 못했습니다.");
        }
        if (requestId !== standardsRequestId) return;

        if (use2022) {
          const previousCourse = course.value || preferredCourse;
          const availableCourses = data.courses || [];
          setSelectOptions(course, availableCourses, "교과 선택", previousCourse);
          preferredCourse = "";

          if (previousCourse && !availableCourses.includes(previousCourse)) {
            standardArea.value = "";
            clearSelectedStandards();
            standardStatus.textContent = "선택한 학년과 과목에 해당하는 데이터가 없습니다. 과목을 다시 선택해 주세요.";
            return;
          }

          const previousArea = standardArea.value;
          setSelectOptions(standardArea, data.areas || [], "전체 영역", previousArea);
        }

        renderStandards(data.standards || []);
        if (!course.value && use2022) {
          standardStatus.textContent = "교과를 선택하면 해당 과목의 성취기준이 표시됩니다.";
        }
      } catch (error) {
        if (requestId !== standardsRequestId) return;
        standardOptions.replaceChildren();
        const message = document.createElement("p");
        message.className = "standard-empty";
        message.textContent = error.message || "성취기준 목록을 불러오지 못했습니다.";
        standardOptions.appendChild(message);
        standardStatus.textContent = "성취기준 조회에 실패했습니다.";
      }
    }

    rebuildCourses();
    loadStandards();

    subjectSelect.addEventListener("change", () => {
      preferredCourse = "";
      course.value = "";
      standardArea.value = "";
      clearSelectedStandards();
      rebuildCourses();
      loadStandards();
    });
    gradeSelect.addEventListener("change", () => {
      preferredCourse = "";
      course.value = "";
      standardArea.value = "";
      clearSelectedStandards();
      rebuildCourses();
      loadStandards();
    });
    curriculum.addEventListener("change", () => {
      preferredCourse = "";
      course.value = "";
      standardArea.value = "";
      clearSelectedStandards();
      rebuildCourses();
      loadStandards();
    });
    course.addEventListener("change", () => {
      preferredCourse = "";
      standardArea.value = "";
      clearSelectedStandards();
      loadStandards();
    });
    standardArea.addEventListener("change", () => loadStandards());

