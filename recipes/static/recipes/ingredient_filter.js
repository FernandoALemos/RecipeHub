(function () {
    const root = document.querySelector(".js-ingredient-filter-combobox");
    const optionsNode = document.getElementById("ingredient-filter-options");
    if (!root || !optionsNode) {
        return;
    }

    const productOptions = JSON.parse(optionsNode.textContent);
    const search = root.querySelector(".js-ingredient-filter-search");
    const list = root.querySelector(".js-ingredient-filter-list");
    const chips = document.querySelector(".js-ingredient-chips");
    if (!search || !list || !chips) {
        return;
    }

    function selectedIds() {
        return Array.from(chips.querySelectorAll('input[name="ingredients"]')).map(
            (input) => input.value
        );
    }

    function filteredProducts(query) {
        const needle = (query || "").trim().toLowerCase();
        const selected = new Set(selectedIds());
        const available = productOptions.filter((product) => !selected.has(product.id));
        if (!needle) {
            return available.slice(0, 40);
        }
        return available
            .filter((product) => product.name.toLowerCase().includes(needle))
            .slice(0, 40);
    }

    function closeList() {
        list.hidden = true;
        list.innerHTML = "";
    }

    function openList(query) {
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

    function activeOption() {
        return list.querySelector(".product-combobox-option.is-active");
    }

    function moveActive(direction) {
        const options = Array.from(list.querySelectorAll(".product-combobox-option"));
        if (!options.length) {
            return;
        }
        const current = activeOption();
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

    function syncChipsVisibility() {
        chips.hidden = selectedIds().length === 0;
    }

    function addIngredient(productId, productName) {
        if (!productId || selectedIds().includes(productId)) {
            search.value = "";
            closeList();
            return;
        }
        const chip = document.createElement("span");
        chip.className = "ingredient-chip";
        chip.dataset.id = productId;

        const label = document.createElement("span");
        label.textContent = productName;

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "ingredient-chip-remove js-remove-ingredient-chip";
        remove.setAttribute("aria-label", `Remove ${productName}`);
        remove.textContent = "×";

        const hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "ingredients";
        hidden.value = productId;

        chip.appendChild(label);
        chip.appendChild(remove);
        chip.appendChild(hidden);
        chips.appendChild(chip);
        syncChipsVisibility();
        search.value = "";
        closeList();
        search.focus();
    }

    search.addEventListener("focus", () => openList(search.value));
    search.addEventListener("input", () => openList(search.value));
    search.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown") {
            event.preventDefault();
            if (list.hidden) {
                openList(search.value);
            }
            moveActive("down");
            return;
        }
        if (event.key === "ArrowUp") {
            event.preventDefault();
            if (list.hidden) {
                openList(search.value);
            }
            moveActive("up");
            return;
        }
        if (event.key === "Enter") {
            const option = activeOption();
            if (!list.hidden && option) {
                event.preventDefault();
                addIngredient(option.dataset.id, option.dataset.name);
            }
            return;
        }
        if (event.key === "Escape") {
            closeList();
        }
    });

    list.addEventListener("mousedown", (event) => {
        const option = event.target.closest(".product-combobox-option");
        if (!option) {
            return;
        }
        event.preventDefault();
        addIngredient(option.dataset.id, option.dataset.name);
    });

    search.addEventListener("blur", () => {
        window.setTimeout(closeList, 120);
    });

    chips.addEventListener("click", (event) => {
        const button = event.target.closest(".js-remove-ingredient-chip");
        if (!button) {
            return;
        }
        const chip = button.closest(".ingredient-chip");
        if (chip) {
            chip.remove();
            syncChipsVisibility();
        }
    });

    syncChipsVisibility();
})();
