(function () {
    const catalogNode = document.getElementById("product-catalog");
    const optionsNode = document.getElementById("product-options");
    if (!catalogNode || !optionsNode) {
        return;
    }
    const catalog = JSON.parse(catalogNode.textContent);
    const productOptions = JSON.parse(optionsNode.textContent);
    const ingredientList = document.getElementById("ingredient-list");
    const ingredientTemplate = document.getElementById("ingredient-template");
    const addIngredient = document.getElementById("add-ingredient");
    const stepList = document.getElementById("step-list");
    const stepTemplate = document.getElementById("step-template");
    const addStep = document.getElementById("add-step");

    function fillUnits(select, productId, preferred) {
        const meta = catalog[productId];
        const current = preferred || "";
        select.innerHTML = "";
        const blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "Unit";
        select.appendChild(blank);
        if (!meta) {
            return;
        }
        const chosen = current && meta.allowed_units.includes(current)
            ? current
            : meta.default_unit;
        meta.allowed_units.forEach((code) => {
            const option = document.createElement("option");
            option.value = code;
            option.textContent = code;
            if (code === chosen) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    }

    function filteredProducts(query) {
        const needle = (query || "").trim().toLowerCase();
        if (!needle) {
            return productOptions.slice();
        }
        return productOptions.filter((product) =>
            product.name.toLowerCase().includes(needle)
        );
    }

    function productNameById(productId) {
        const match = productOptions.find((product) => product.id === productId);
        return match ? match.name : "";
    }

    function closeList(list) {
        list.hidden = true;
        list.innerHTML = "";
    }

    function openList(combobox, query) {
        const list = combobox.querySelector(".js-product-list");
        const matches = filteredProducts(query);
        list.innerHTML = "";
        if (!matches.length) {
            const empty = document.createElement("li");
            empty.className = "product-combobox-empty";
            empty.textContent = "No products found";
            list.appendChild(empty);
            list.hidden = false;
            return;
        }
        matches.forEach((product, index) => {
            const item = document.createElement("li");
            const button = document.createElement("button");
            button.type = "button";
            button.className = "product-combobox-option";
            button.dataset.id = product.id;
            button.dataset.name = product.name;
            button.textContent = product.name;
            if (index === 0) {
                button.classList.add("is-active");
            }
            item.appendChild(button);
            list.appendChild(item);
        });
        list.hidden = false;
    }

    function activeOption(list) {
        return list.querySelector(".product-combobox-option.is-active");
    }

    function moveActive(list, direction) {
        const options = Array.from(list.querySelectorAll(".product-combobox-option"));
        if (!options.length) {
            return;
        }
        const current = activeOption(list);
        let index = options.indexOf(current);
        index = direction === "down" ? index + 1 : index - 1;
        if (index < 0) {
            index = options.length - 1;
        }
        if (index >= options.length) {
            index = 0;
        }
        options.forEach((option) => option.classList.remove("is-active"));
        options[index].classList.add("is-active");
        options[index].scrollIntoView({ block: "nearest" });
    }

    function selectProduct(row, productId, productName) {
        const hidden = row.querySelector(".js-product");
        const search = row.querySelector(".js-product-search");
        const list = row.querySelector(".js-product-list");
        const unitSelect = row.querySelector(".js-unit");
        hidden.value = productId || "";
        search.value = productName || "";
        closeList(list);
        unitSelect.dataset.selected = "";
        fillUnits(unitSelect, hidden.value, "");
        hidden.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function bindProductCombobox(row) {
        const combobox = row.querySelector(".js-product-combobox");
        if (!combobox || combobox.dataset.bound === "1") {
            return;
        }
        combobox.dataset.bound = "1";
        const hidden = combobox.querySelector(".js-product");
        const search = combobox.querySelector(".js-product-search");
        const list = combobox.querySelector(".js-product-list");

        search.addEventListener("focus", () => {
            openList(combobox, search.value);
        });

        search.addEventListener("input", () => {
            if (hidden.value && search.value !== productNameById(hidden.value)) {
                hidden.value = "";
                const unitSelect = row.querySelector(".js-unit");
                unitSelect.dataset.selected = "";
                fillUnits(unitSelect, "", "");
            }
            openList(combobox, search.value);
        });

        search.addEventListener("keydown", (event) => {
            if (event.key === "ArrowDown") {
                event.preventDefault();
                if (list.hidden) {
                    openList(combobox, search.value);
                }
                moveActive(list, "down");
                return;
            }
            if (event.key === "ArrowUp") {
                event.preventDefault();
                if (list.hidden) {
                    openList(combobox, search.value);
                }
                moveActive(list, "up");
                return;
            }
            if (event.key === "Enter") {
                const option = activeOption(list);
                if (!list.hidden && option) {
                    event.preventDefault();
                    selectProduct(row, option.dataset.id, option.dataset.name);
                }
                return;
            }
            if (event.key === "Escape") {
                closeList(list);
                if (hidden.value) {
                    search.value = productNameById(hidden.value);
                }
            }
        });

        list.addEventListener("mousedown", (event) => {
            const option = event.target.closest(".product-combobox-option");
            if (!option) {
                return;
            }
            event.preventDefault();
            selectProduct(row, option.dataset.id, option.dataset.name);
        });

        search.addEventListener("blur", () => {
            window.setTimeout(() => {
                closeList(list);
                if (hidden.value) {
                    search.value = productNameById(hidden.value);
                } else if (search.value.trim()) {
                    const exact = productOptions.find(
                        (product) => product.name.toLowerCase() === search.value.trim().toLowerCase()
                    );
                    if (exact) {
                        selectProduct(row, exact.id, exact.name);
                    } else {
                        search.value = "";
                    }
                }
            }, 120);
        });
    }

    function bindIngredient(row) {
        const productSelect = row.querySelector(".js-product");
        const unitSelect = row.querySelector(".js-unit");
        const remove = row.querySelector(".js-remove-ingredient");
        bindProductCombobox(row);
        if (productSelect && unitSelect) {
            fillUnits(unitSelect, productSelect.value, unitSelect.dataset.selected || unitSelect.value);
        }
        if (remove) {
            remove.addEventListener("click", () => {
                const rows = ingredientList.querySelectorAll(".ingredient-row");
                if (rows.length === 1) {
                    selectProduct(row, "", "");
                    row.querySelector('[name="ingredient_quantity"]').value = "";
                    row.querySelector('[name="ingredient_preparation"]').value = "";
                    return;
                }
                row.remove();
            });
        }
    }

    function refreshStepNumbers() {
        stepList.querySelectorAll(".step-row").forEach((row, index) => {
            const label = row.querySelector(".js-step-number");
            if (label) {
                label.textContent = String(index + 1);
            }
        });
    }

    function bindStep(row) {
        const remove = row.querySelector(".js-remove-step");
        const moveUp = row.querySelector(".js-move-step-up");
        const moveDown = row.querySelector(".js-move-step-down");
        if (moveUp) {
            moveUp.addEventListener("click", () => {
                const previous = row.previousElementSibling;
                if (previous) {
                    stepList.insertBefore(row, previous);
                    refreshStepNumbers();
                }
            });
        }
        if (moveDown) {
            moveDown.addEventListener("click", () => {
                const next = row.nextElementSibling;
                if (next) {
                    stepList.insertBefore(next, row);
                    refreshStepNumbers();
                }
            });
        }
        if (!remove) {
            return;
        }
        remove.addEventListener("click", () => {
            const rows = stepList.querySelectorAll(".step-row");
            if (rows.length === 1) {
                row.querySelector('[name="step_description"]').value = "";
                return;
            }
            row.remove();
            refreshStepNumbers();
        });
    }

    ingredientList.querySelectorAll(".ingredient-row").forEach(bindIngredient);
    stepList.querySelectorAll(".step-row").forEach(bindStep);

    addIngredient.addEventListener("click", () => {
        const row = ingredientTemplate.content.firstElementChild.cloneNode(true);
        ingredientList.appendChild(row);
        bindIngredient(row);
    });

    addStep.addEventListener("click", () => {
        const row = stepTemplate.content.firstElementChild.cloneNode(true);
        stepList.appendChild(row);
        bindStep(row);
        refreshStepNumbers();
    });
})();
