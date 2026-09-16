class FamilyTodoPanel extends HTMLElement {
  constructor() {
    super();
    // Riktig shadow root krävs för att våra generiska tagg-/klassväljare
    // (button, input, h1, *, ...) ska stanna kvar inuti panelen istället
    // för att läcka ut och gälla globalt i hela HA-appen (se cal_combiner-
    // panelens motsvarande kommentar - samma bugg, samma fix).
    this.attachShadow({ mode: "open" });
    this._lists = [];
    this._persons = [];
    this._areas = [];
    this._floors = []; // HA:s våningar, sorterade lägsta först - se _groupSectionsByFloor
    this._notifyServices = []; // notify.*-tjänster, för Notiser-tabben
    this._notifyMap = {}; // person entity_id -> notify service
    this._items = {}; // entry_id -> items[]
    this._sections = {}; // entry_id -> sections[]
    this._activeListId = null;
    this._openItems = {}; // uid -> bool (delsteg/tilldelning expanderat)
    this._copyPickerOpen = {}; // uid -> bool (kopiera-till-rum-väljaren expanderad)
    this._addingSection = false;
    this._initialized = false;
    this._haUsers = []; // HA-konton, för "Ägare"-väljaren - se _reloadLists/_mkUserPicker
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._boot();
    }
  }

  get hass() {
    return this._hass;
  }

  async _boot() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; box-sizing: border-box; min-height: 100%; padding: 16px;
          max-width: 720px; margin: 0 auto;
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
        *, *::before, *::after { box-sizing: border-box; }
        h1 { font-size: 24px; font-weight: 400; color: var(--primary-text-color); margin: 4px 0 4px 0;
          display: flex; align-items: center; gap: 10px; }
        h1 ha-icon { --mdc-icon-size: 28px; color: var(--primary-color); }
        p.subtitle { color: var(--secondary-text-color); margin-top: 0; margin-bottom: 20px; }
        .ft-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
        .ft-tab { display: flex; align-items: center; gap: 6px; padding: 6px 14px; cursor: pointer;
          background: var(--secondary-background-color, #eee); border: 1px solid transparent; border-radius: 999px;
          font-size: 13px; color: var(--primary-text-color); }
        .ft-tab.active { background: var(--primary-color); color: var(--text-primary-color, white); }
        .ft-tab-new { background: transparent; border: 1px dashed var(--divider-color, #ccc);
          color: var(--secondary-text-color); }
        .ft-tab ha-icon { --mdc-icon-size: 16px; }
        .ft-card { background: var(--card-background-color, white); border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,0.1)); padding: 16px; margin-bottom: 16px;
          border: 1px solid var(--ha-card-border-color, transparent); }
        .ft-card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
        .ft-card-header ha-icon { --mdc-icon-size: 24px; color: var(--primary-color); flex-shrink: 0; }
        .ft-card-header input[type="text"].ft-name { font-size: 16px; font-weight: 500; flex: 1; }
        .ft-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
        input[type="text"], input[type="date"], input[type="time"], select {
          padding: 8px 10px; border-radius: 6px; min-width: 120px;
          border: 1px solid var(--divider-color, #ccc); background: var(--card-background-color);
          color: var(--primary-text-color); font-size: 14px; box-sizing: border-box; }
        input[type="text"] { flex: 1; }
        button { border: none; border-radius: 6px; padding: 8px 14px; font-size: 14px; cursor: pointer;
          background: var(--primary-color); color: var(--text-primary-color, white); }
        button.secondary { background: transparent; color: var(--primary-color);
          border: 1px solid var(--primary-color); }
        button.danger { background: var(--error-color, #db4437); color: white; }
        button.text { background: none; color: var(--primary-color); padding: 4px 8px; }
        button:disabled { opacity: .4; cursor: default; }
        .ft-item { border-bottom: 1px solid var(--divider-color, #eee); padding: 8px 0; }
        .ft-item:last-child { border-bottom: none; }
        .ft-item-row { display: flex; align-items: center; gap: 8px; }
        .ft-item-row input[type="checkbox"] { width: 20px; height: 20px; flex-shrink: 0; cursor: pointer; }
        .ft-item-summary { flex: 1; font-size: 14px; cursor: pointer; }
        .ft-item-summary.done { text-decoration: line-through; color: var(--secondary-text-color); }
        .ft-item-meta { font-size: 12px; color: var(--secondary-text-color); margin-left: 28px; margin-top: 2px;
          display: flex; gap: 10px; flex-wrap: wrap; }
        .ft-item-detail { margin-left: 28px; margin-top: 8px; padding: 10px; border-radius: 8px;
          background: var(--secondary-background-color, #f4f4f4); }
        .ft-subtask-row { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
        .ft-subtask-row input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; }
        .ft-subtask-row span.done { text-decoration: line-through; color: var(--secondary-text-color); }
        .ft-empty { color: var(--secondary-text-color); font-size: 14px; padding: 12px 0; }
        .ft-progress { font-size: 11px; padding: 1px 6px; border-radius: 999px;
          background: var(--secondary-background-color, #eee); color: var(--secondary-text-color); }
        .ft-section { margin-top: 18px; }
        .ft-section:first-of-type { margin-top: 8px; }
        .ft-section-header { display: flex; align-items: center; gap: 8px; padding: 6px 0;
          border-bottom: 1px solid var(--divider-color, #ddd); margin-bottom: 4px; }
        .ft-section-header ha-icon { --mdc-icon-size: 18px; color: var(--secondary-text-color); }
        .ft-section-header .ft-section-name { font-weight: 500; font-size: 13px; flex: 1;
          color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .02em; }
        .ft-section-header button.text { padding: 2px 4px; }
        .ft-floor-header { display: flex; align-items: center; gap: 8px; margin-top: 24px;
          padding-bottom: 4px; font-weight: 600; font-size: 15px; color: var(--primary-text-color); }
        .ft-floor-header:first-child { margin-top: 8px; }
        .ft-floor-header ha-icon { --mdc-icon-size: 20px; color: var(--primary-color); }
        .ft-section-add { border: 1px dashed var(--divider-color, #ccc); border-radius: 8px; padding: 10px;
          margin-top: 12px; }
      </style>
      <h1><ha-icon icon="mdi:format-list-checks"></ha-icon>Att göra</h1>
      <p class="subtitle">Skapa listor här - varje lista blir en riktig todo-lista i Home Assistant
        (funkar med röstassistenten och det inbyggda todo-kortet). Delsteg och tilldelning per uppgift
        finns bara här i panelen.</p>
      <div class="ft-tabs" id="tabs"></div>
      <div id="content"></div>
    `;
    await this._reloadLists();
  }

  async _reloadLists() {
    const [{ lists }, { persons }, { areas }, { floors }] = await Promise.all([
      this._hass.callWS({ type: "family_todo/list_lists" }),
      this._hass.callWS({ type: "family_todo/list_persons" }),
      this._hass.callWS({ type: "family_todo/list_areas" }),
      this._hass.callWS({ type: "family_todo/list_floors" }),
    ]);
    this._lists = lists;
    this._persons = persons;
    this._areas = areas;
    this._floors = floors;
    // Kräver adminrättigheter - en icke-admin som öppnar panelen
    // (require_admin=False) faller tyst tillbaka på fritext för Ägare
    // istället (samma mönster som family-planner-panel.js:s _mkUserPicker).
    try {
      const users = await this._hass.callWS({ type: "config/auth/list" });
      this._haUsers = Array.isArray(users) ? users : [];
    } catch (err) {
      this._haUsers = [];
    }
    const isFixedTab = this._activeListId === "__new__" || this._activeListId === "__notify__";
    if (!this._activeListId || (!isFixedTab && !lists.find((l) => l.entry_id === this._activeListId))) {
      this._activeListId = lists.length ? lists[0].entry_id : "__new__";
    }
    if (this._activeListId !== "__new__") {
      await this._reloadItems(this._activeListId);
    }
    this._render();
  }

  async _reloadNotifySettings() {
    const [{ services }, { map }] = await Promise.all([
      this._hass.callWS({ type: "family_todo/list_notify_services" }),
      this._hass.callWS({ type: "family_todo/get_notify_map" }),
    ]);
    this._notifyServices = services;
    this._notifyMap = map;
  }

  async _reloadItems(entryId) {
    const [{ items }, { sections }] = await Promise.all([
      this._hass.callWS({ type: "family_todo/list_items", entry_id: entryId }),
      this._hass.callWS({ type: "family_todo/list_sections", entry_id: entryId }),
    ]);
    this._items[entryId] = items;
    this._sections[entryId] = sections;
  }

  _areaIcon(areaId) {
    const area = this._areas.find((a) => a.area_id === areaId);
    return (area && area.icon) || "mdi:floor-plan";
  }

  // Våningen (om någon) sektionens kopplade HA-area tillhör - en sektion
  // utan area, eller vars area inte är satt till någon våning, har ingen
  // resolverbar våning (hamnar i _groupSectionsByFloor:s sista, namnlösa
  // grupp - dit "Ute" bör hamna eftersom den sektionen saknar area helt).
  _sectionFloor(section) {
    if (!section || !section.area_id) return null;
    const area = this._areas.find((a) => a.area_id === section.area_id);
    if (!area || !area.floor_id) return null;
    return this._floors.find((f) => f.floor_id === area.floor_id) || null;
  }

  // Grupperar en listas sektioner per våning, i samma ordning som
  // this._floors (lägsta våning först, se ws_list_floors). Sektioner utan
  // resolverbar våning hamnar samlade i en sista grupp (floor: null) -
  // det är den gruppen "Ute" landar i, eftersom den sektionen inte är
  // kopplad till någon HA-area alls.
  _groupSectionsByFloor(sections) {
    const byFloorId = new Map();
    const noFloor = [];
    for (const section of sections) {
      const floor = this._sectionFloor(section);
      if (!floor) {
        noFloor.push(section);
        continue;
      }
      if (!byFloorId.has(floor.floor_id)) byFloorId.set(floor.floor_id, { floor, sections: [] });
      byFloorId.get(floor.floor_id).sections.push(section);
    }
    const groups = this._floors.filter((f) => byFloorId.has(f.floor_id)).map((f) => byFloorId.get(f.floor_id));
    if (noFloor.length) groups.push({ floor: null, sections: noFloor });
    return groups;
  }

  _render() {
    this._renderTabs();
    this._renderContent();
  }

  _renderTabs() {
    const tabs = this.shadowRoot.getElementById("tabs");
    tabs.innerHTML = "";
    for (const list of this._lists) {
      const btn = document.createElement("button");
      btn.className = "ft-tab" + (this._activeListId === list.entry_id ? " active" : "");
      btn.innerHTML = `<ha-icon icon="${list.icon || "mdi:format-list-checks"}"></ha-icon>`;
      btn.append(list.name);
      btn.addEventListener("click", async () => {
        this._activeListId = list.entry_id;
        this._addingSection = false;
        await this._reloadItems(list.entry_id);
        this._render();
      });
      tabs.appendChild(btn);
    }
    const notifyBtn = document.createElement("button");
    notifyBtn.className = "ft-tab" + (this._activeListId === "__notify__" ? " active" : "");
    notifyBtn.innerHTML = `<ha-icon icon="mdi:bell-outline"></ha-icon>Notiser`;
    notifyBtn.addEventListener("click", async () => {
      this._activeListId = "__notify__";
      this._addingSection = false;
      await this._reloadNotifySettings();
      this._render();
    });
    tabs.appendChild(notifyBtn);

    const newBtn = document.createElement("button");
    newBtn.className = "ft-tab ft-tab-new" + (this._activeListId === "__new__" ? " active" : "");
    newBtn.innerHTML = `<ha-icon icon="mdi:plus"></ha-icon>Ny lista`;
    newBtn.addEventListener("click", () => {
      this._activeListId = "__new__";
      this._addingSection = false;
      this._render();
    });
    tabs.appendChild(newBtn);
  }

  _renderContent() {
    const content = this.shadowRoot.getElementById("content");
    content.innerHTML = "";
    if (this._activeListId === "__new__") {
      content.appendChild(this._renderNewListCard());
      return;
    }
    if (this._activeListId === "__notify__") {
      content.appendChild(this._renderNotifyCard());
      return;
    }
    const list = this._lists.find((l) => l.entry_id === this._activeListId);
    if (!list) return;
    content.appendChild(this._renderListCard(list));
  }

  _renderNotifyCard() {
    const card = document.createElement("div");
    card.className = "ft-card";
    card.innerHTML = `
      <div class="ft-card-header"><ha-icon icon="mdi:bell-outline"></ha-icon>
        <span class="ft-name">Notiser</span>
      </div>
      <p class="subtitle" style="margin-top:0;">Koppla varje person till sin mobilpush
        (Inställningar → Enheter &amp; tjänster → Mobilapp, om HA-appen är installerad på
        deras telefon). En uppgift som är tilldelad en kopplad person och har en <em>tid</em>
        satt på förfallodatumet (inte bara ett datum) skickar då en påminnelse dit automatiskt,
        om uppgiften fortfarande inte är avbockad när tiden är inne.</p>
    `;
    if (!this._persons.length) {
      const empty = document.createElement("div");
      empty.className = "ft-empty";
      empty.textContent = "Inga person.*-entiteter hittades i Home Assistant.";
      card.appendChild(empty);
      return card;
    }
    for (const person of this._persons) {
      const row = document.createElement("div");
      row.className = "ft-row";
      const label = document.createElement("span");
      label.style.cssText = "min-width:120px;";
      label.textContent = `${person.name}:`;
      row.appendChild(label);
      const select = document.createElement("select");
      select.innerHTML =
        `<option value="">Ingen påminnelse</option>` +
        this._notifyServices.map((s) => `<option value="${_esc(s)}">${_esc(s)}</option>`).join("");
      select.value = this._notifyMap[person.entity_id] || "";
      select.addEventListener("change", async () => {
        await this._hass.callWS({
          type: "family_todo/set_notify_target",
          person_entity_id: person.entity_id,
          service: select.value || null,
        });
        this._notifyMap = { ...this._notifyMap, [person.entity_id]: select.value };
        testBtn.disabled = !select.value;
        status.textContent = "";
      });
      row.appendChild(select);

      const testBtn = document.createElement("button");
      testBtn.className = "text";
      testBtn.innerHTML = `<ha-icon icon="mdi:bell-ring-outline"></ha-icon> Skicka test`;
      testBtn.disabled = !select.value;
      const status = document.createElement("span");
      status.style.cssText = "font-size:12px; margin-left:6px;";
      testBtn.addEventListener("click", async () => {
        testBtn.disabled = true;
        status.textContent = "Skickar…";
        status.style.color = "var(--secondary-text-color)";
        try {
          await this._hass.callWS({ type: "family_todo/send_test_notification", service: select.value });
          status.textContent = "✅ Skickad";
          status.style.color = "var(--success-color, green)";
        } catch (err) {
          status.textContent = `❌ ${(err && err.message) || "Kunde inte skicka"}`;
          status.style.color = "var(--error-color, red)";
        }
        testBtn.disabled = !select.value;
      });
      row.appendChild(testBtn);
      row.appendChild(status);

      card.appendChild(row);
    }
    return card;
  }

  _renderNewListCard() {
    const card = document.createElement("div");
    card.className = "ft-card";
    card.innerHTML = `
      <div class="ft-card-header"><ha-icon icon="mdi:plus"></ha-icon>
        <input type="text" class="ft-name" id="new-name" placeholder="Namn på ny lista, t.ex. Inköp" />
      </div>
      <div class="ft-actions"><button id="new-create">Skapa lista</button></div>
    `;
    card.querySelector("#new-create").addEventListener("click", async () => {
      const nameInput = card.querySelector("#new-name");
      const name = nameInput.value.trim();
      if (!name) return;
      const { entry_id } = await this._hass.callWS({ type: "family_todo/create_list", name });
      this._activeListId = entry_id;
      await this._reloadLists();
    });
    return card;
  }

  // HA-kontoväljare för "Ägare" - styr vem som får redigera listan när den
  // inloggade är markerad som barn i Family Planner (se permissions.py i
  // integrationen). Samma mönster som family-planner-panel.js:s
  // _mkUserPicker, duplicerad här eftersom panelerna inte delar kod.
  _mkUserPicker(value, onChange) {
    if (this._haUsers.length === 0) {
      const input = document.createElement("input");
      input.type = "text";
      input.placeholder = "user_id";
      input.value = value || "";
      input.addEventListener("change", () => onChange(input.value.trim() || null));
      return input;
    }
    const select = document.createElement("select");
    const noneOpt = document.createElement("option");
    noneOpt.value = "";
    noneOpt.textContent = "(ingen - delad/gemensam lista)";
    select.appendChild(noneOpt);
    let matched = !value;
    this._haUsers.forEach((u) => {
      const opt = document.createElement("option");
      opt.value = u.id;
      opt.textContent = u.name || u.id;
      if (u.id === value) {
        opt.selected = true;
        matched = true;
      }
      select.appendChild(opt);
    });
    if (value && !matched) {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = `${value} (okänt konto)`;
      opt.selected = true;
      select.appendChild(opt);
    }
    select.addEventListener("change", () => onChange(select.value || null));
    return select;
  }

  _renderListCard(list) {
    const items = this._items[list.entry_id] || [];
    const card = document.createElement("div");
    card.className = "ft-card";

    const header = document.createElement("div");
    header.className = "ft-card-header";
    header.innerHTML = `<ha-icon icon="${list.icon || "mdi:format-list-checks"}"></ha-icon>
      <input type="text" class="ft-name" value="${_esc(list.name)}" />`;
    const nameInput = header.querySelector("input");
    nameInput.addEventListener("change", async () => {
      const name = nameInput.value.trim();
      if (!name) return;
      await this._hass.callWS({
        type: "family_todo/update_list",
        entry_id: list.entry_id,
        name,
        icon: list.icon,
        color: list.color,
        owner_user_id: list.owner_user_id,
      });
      await this._reloadLists();
    });

    const ownerRow = document.createElement("div");
    ownerRow.className = "ft-row";
    const ownerLabel = document.createElement("span");
    ownerLabel.textContent = "Ägare: ";
    ownerLabel.style.fontSize = "13px";
    ownerLabel.style.color = "var(--secondary-text-color)";
    ownerRow.appendChild(ownerLabel);
    ownerRow.appendChild(
      this._mkUserPicker(list.owner_user_id, async (val) => {
        await this._hass.callWS({
          type: "family_todo/update_list",
          entry_id: list.entry_id,
          name: list.name,
          icon: list.icon,
          color: list.color,
          owner_user_id: val,
        });
        await this._reloadLists();
      })
    );
    header.appendChild(ownerRow);

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "danger";
    deleteBtn.textContent = "Ta bort lista";
    deleteBtn.addEventListener("click", async () => {
      if (!confirm(`Ta bort listan "${list.name}" och alla dess uppgifter?`)) return;
      await this._hass.callWS({ type: "family_todo/delete_list", entry_id: list.entry_id });
      this._activeListId = null;
      await this._reloadLists();
    });
    header.appendChild(deleteBtn);
    card.appendChild(header);

    const sections = this._sections[list.entry_id] || [];

    const addRow = document.createElement("div");
    addRow.className = "ft-row";
    const sectionOptions =
      `<option value="">Ingen sektion</option>` +
      sections.map((s) => `<option value="${_esc(s.id)}">${_esc(s.name)}</option>`).join("");
    addRow.innerHTML = `<input type="text" id="add-summary" placeholder="Ny uppgift..." />
      ${sections.length ? `<select id="add-section">${sectionOptions}</select>` : ""}
      <button id="add-btn">Lägg till</button>`;
    const doAdd = async () => {
      const input = addRow.querySelector("#add-summary");
      const summary = input.value.trim();
      if (!summary) return;
      const sectionSelect = addRow.querySelector("#add-section");
      input.value = "";
      await this._hass.callWS({
        type: "family_todo/create_item",
        entry_id: list.entry_id,
        summary,
        section_id: sectionSelect ? sectionSelect.value || null : null,
      });
      await this._reloadItems(list.entry_id);
      this._render();
    };
    addRow.querySelector("#add-btn").addEventListener("click", doAdd);
    addRow.querySelector("#add-summary").addEventListener("keydown", (e) => {
      if (e.key === "Enter") doAdd();
    });
    card.appendChild(addRow);

    if (!items.length && !sections.length) {
      const empty = document.createElement("div");
      empty.className = "ft-empty";
      empty.textContent = "Inga uppgifter än.";
      card.appendChild(empty);
    }

    if (!sections.length) {
      // Inga sektioner skapade - visa uppgifterna som en enkel platt lista,
      // precis som innan sektioner fanns, istället för att tvinga fram en
      // "Utan sektion"-rubrik ingen bett om.
      for (const item of items) {
        card.appendChild(this._renderItem(list, item));
      }
    } else {
      for (const group of this._groupSectionsByFloor(sections)) {
        if (group.floor) {
          const floorHeader = document.createElement("div");
          floorHeader.className = "ft-floor-header";
          floorHeader.innerHTML = `<ha-icon icon="${group.floor.icon || "mdi:layers-outline"}"></ha-icon><span>${_esc(group.floor.name)}</span>`;
          card.appendChild(floorHeader);
        }
        for (const section of group.sections) {
          card.appendChild(this._renderSectionGroup(list, section, items.filter((i) => i.section_id === section.id)));
        }
      }
      const unsectioned = items.filter((i) => !i.section_id);
      if (unsectioned.length) {
        card.appendChild(this._renderSectionGroup(list, null, unsectioned));
      }
    }

    card.appendChild(this._renderSectionAdd(list));

    return card;
  }

  _renderSectionGroup(list, section, items) {
    const group = document.createElement("div");
    group.className = "ft-section";

    const header = document.createElement("div");
    header.className = "ft-section-header";
    if (section) {
      header.innerHTML = `<ha-icon icon="${section.icon || this._areaIcon(section.area_id)}"></ha-icon>
        <span class="ft-section-name">${_esc(section.name)}</span>`;
      const editBtn = document.createElement("button");
      editBtn.className = "text";
      editBtn.innerHTML = `<ha-icon icon="mdi:pencil-outline"></ha-icon>`;
      editBtn.addEventListener("click", () => this._promptEditSection(list, section));
      header.appendChild(editBtn);
      const deleteBtn = document.createElement("button");
      deleteBtn.className = "text";
      deleteBtn.innerHTML = `<ha-icon icon="mdi:delete-outline"></ha-icon>`;
      deleteBtn.addEventListener("click", async () => {
        if (!confirm(`Ta bort sektionen "${section.name}"? Uppgifterna i den tas inte bort.`)) return;
        await this._hass.callWS({ type: "family_todo/delete_section", entry_id: list.entry_id, section_id: section.id });
        await this._reloadItems(list.entry_id);
        this._render();
      });
      header.appendChild(deleteBtn);
    } else {
      header.innerHTML = `<ha-icon icon="mdi:tray"></ha-icon><span class="ft-section-name">Utan sektion</span>`;
    }
    group.appendChild(header);

    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "ft-empty";
      empty.textContent = "Inga uppgifter här.";
      group.appendChild(empty);
    }
    for (const item of items) {
      group.appendChild(this._renderItem(list, item));
    }
    return group;
  }

  _renderSectionAdd(list) {
    const wrap = document.createElement("div");
    if (!this._addingSection) {
      const btn = document.createElement("button");
      btn.className = "secondary";
      btn.innerHTML = `<ha-icon icon="mdi:plus"></ha-icon> Ny sektion`;
      btn.style.marginTop = "12px";
      btn.addEventListener("click", () => {
        this._addingSection = true;
        this._render();
      });
      wrap.appendChild(btn);
      return wrap;
    }

    const box = document.createElement("div");
    box.className = "ft-section-add";
    const areaOptions =
      `<option value="">Ingen area (fritt namn)</option>` +
      this._areas.map((a) => `<option value="${_esc(a.area_id)}">${_esc(a.name)}</option>`).join("");
    box.innerHTML = `
      <div class="ft-row">
        <input type="text" id="section-name" placeholder="Namn, t.ex. Kök" />
        <select id="section-area">${areaOptions}</select>
      </div>
      <div class="ft-actions">
        <button id="section-save">Skapa sektion</button>
        <button id="section-cancel" class="secondary">Avbryt</button>
      </div>
    `;
    const areaSelect = box.querySelector("#section-area");
    const nameInput = box.querySelector("#section-name");
    areaSelect.addEventListener("change", () => {
      // Area vald: föreslå areans namn om användaren inte redan skrivit något eget.
      if (!nameInput.value.trim()) {
        const area = this._areas.find((a) => a.area_id === areaSelect.value);
        if (area) nameInput.value = area.name;
      }
    });
    box.querySelector("#section-cancel").addEventListener("click", () => {
      this._addingSection = false;
      this._render();
    });
    box.querySelector("#section-save").addEventListener("click", async () => {
      const name = nameInput.value.trim();
      if (!name) return;
      await this._hass.callWS({
        type: "family_todo/create_section",
        entry_id: list.entry_id,
        name,
        area_id: areaSelect.value || null,
      });
      this._addingSection = false;
      await this._reloadItems(list.entry_id);
      this._render();
    });
    wrap.appendChild(box);
    return wrap;
  }

  _promptEditSection(list, section) {
    const name = prompt("Namn på sektionen:", section.name);
    if (name === null) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    this._hass
      .callWS({
        type: "family_todo/update_section",
        entry_id: list.entry_id,
        section_id: section.id,
        name: trimmed,
        area_id: section.area_id,
        icon: section.icon,
      })
      .then(async () => {
        await this._reloadItems(list.entry_id);
        this._render();
      });
  }

  // Kryssrutelista med listans övriga sektioner ("rum") - "Kopiera hit"
  // skapar en fristående kopia av uppgiften i varje ikryssad sektion, se
  // family_todo/copy_item i ws_api.py. Källuppgiften rörs inte.
  _renderCopyPicker(list, item) {
    const box = document.createElement("div");
    box.className = "ft-item-detail";

    const sections = this._sections[list.entry_id] || [];
    const targets = sections.filter((s) => s.id !== item.section_id);
    if (targets.length === 0) {
      box.innerHTML = `<div class="ft-empty">Inga andra rum i den här listan.</div>`;
      return box;
    }

    const checkboxes = targets.map((s) => {
      const label = document.createElement("label");
      label.style.display = "flex";
      label.style.alignItems = "center";
      label.style.gap = "6px";
      label.style.marginBottom = "6px";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = s.id;
      label.appendChild(cb);
      label.appendChild(document.createTextNode(s.name));
      box.appendChild(label);
      return cb;
    });

    const confirmBtn = document.createElement("button");
    confirmBtn.textContent = "Kopiera hit";
    confirmBtn.addEventListener("click", async () => {
      const sectionIds = checkboxes.filter((c) => c.checked).map((c) => c.value);
      if (sectionIds.length === 0) return;
      await this._hass.callWS({
        type: "family_todo/copy_item",
        entry_id: list.entry_id,
        uid: item.uid,
        section_ids: sectionIds,
      });
      this._copyPickerOpen[item.uid] = false;
      await this._reloadItems(list.entry_id);
      this._render();
    });
    box.appendChild(confirmBtn);

    return box;
  }

  _renderItem(list, item) {
    const wrap = document.createElement("div");
    wrap.className = "ft-item";
    const done = item.status === "completed";

    const row = document.createElement("div");
    row.className = "ft-item-row";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = done;
    checkbox.addEventListener("change", async () => {
      await this._hass.callWS({
        type: "family_todo/update_item",
        entry_id: list.entry_id,
        uid: item.uid,
        summary: item.summary,
        status: checkbox.checked ? "completed" : "needs_action",
        description: item.description,
        due: item.due,
      });
      await this._reloadItems(list.entry_id);
      this._render();
    });
    row.appendChild(checkbox);

    const summary = document.createElement("div");
    summary.className = "ft-item-summary" + (done ? " done" : "");
    summary.textContent = item.summary;
    summary.title = "Klicka för att visa delsteg och tilldelning";
    summary.addEventListener("click", () => {
      this._openItems[item.uid] = !this._openItems[item.uid];
      this._render();
    });
    row.appendChild(summary);

    if (item.subtasks_total > 0) {
      const badge = document.createElement("span");
      badge.className = "ft-progress";
      badge.textContent = `${item.subtasks_done}/${item.subtasks_total}`;
      row.appendChild(badge);
    }

    // Kopiera till andra rum - skapar en helt fristående kopia (eget uid,
    // egen avbockning) i valda sektioner inom samma lista, se
    // _renderCopyPicker/family_todo/copy_item. Bara relevant för listor med
    // fler än en sektion att kopiera till.
    const sectionsInList = this._sections[list.entry_id] || [];
    if (sectionsInList.length > 1) {
      const copyBtn = document.createElement("button");
      copyBtn.className = "text";
      copyBtn.innerHTML = `<ha-icon icon="mdi:content-copy"></ha-icon>`;
      copyBtn.title = "Kopiera till andra rum";
      copyBtn.addEventListener("click", () => {
        this._copyPickerOpen[item.uid] = !this._copyPickerOpen[item.uid];
        this._render();
      });
      row.appendChild(copyBtn);
    }

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "text";
    deleteBtn.innerHTML = `<ha-icon icon="mdi:delete-outline"></ha-icon>`;
    deleteBtn.addEventListener("click", async () => {
      await this._hass.callWS({ type: "family_todo/delete_item", entry_id: list.entry_id, uid: item.uid });
      await this._reloadItems(list.entry_id);
      this._render();
    });
    row.appendChild(deleteBtn);

    wrap.appendChild(row);

    if (this._copyPickerOpen[item.uid]) {
      wrap.appendChild(this._renderCopyPicker(list, item));
    }

    if (item.assignee || item.due || item.recurrence || item.last_completed) {
      const meta = document.createElement("div");
      meta.className = "ft-item-meta";
      if (item.assignee) meta.innerHTML += `<span><ha-icon icon="mdi:account"></ha-icon> ${_esc(item.assignee)}</span>`;
      if (item.due) {
        const duePrefix = item.recurrence ? "Nästa: " : "";
        meta.innerHTML += `<span><ha-icon icon="mdi:calendar"></ha-icon> ${duePrefix}${_esc(_formatDue(item.due))}</span>`;
        if (_hasDueTime(item.due) && !done) {
          const label = item.reminder_sent ? "Påminnelse skickad" : "Påminnelse skickas om inte avbockad";
          meta.innerHTML += `<span title="${_esc(label)}"><ha-icon icon="${item.reminder_sent ? "mdi:bell-check-outline" : "mdi:bell-outline"}"></ha-icon></span>`;
        }
      }
      if (item.recurrence)
        meta.innerHTML += `<span><ha-icon icon="mdi:repeat"></ha-icon> ${_esc(_recurrenceLabel(item.recurrence))}</span>`;
      if (item.last_completed)
        meta.innerHTML += `<span><ha-icon icon="mdi:check"></ha-icon> Senast: ${_esc(item.last_completed)}</span>`;
      wrap.appendChild(meta);
    }

    if (this._openItems[item.uid]) {
      wrap.appendChild(this._renderItemDetail(list, item));
    }

    return wrap;
  }

  _renderRecurrenceEditor(list, item) {
    const row = document.createElement("div");
    row.className = "ft-row";
    const hasRecurrence = !!item.recurrence;

    const label = document.createElement("label");
    label.style.cssText = "display:flex;align-items:center;gap:6px;";
    const enabledCb = document.createElement("input");
    enabledCb.type = "checkbox";
    enabledCb.checked = hasRecurrence;
    label.appendChild(enabledCb);
    label.append("Återkommande");
    row.appendChild(label);

    const intervalInput = document.createElement("input");
    intervalInput.type = "number";
    intervalInput.min = "1";
    intervalInput.value = hasRecurrence ? item.recurrence.interval : 2;
    intervalInput.style.cssText = "width:60px;min-width:60px;";
    intervalInput.disabled = !hasRecurrence;
    row.appendChild(intervalInput);

    const unitSelect = document.createElement("select");
    unitSelect.innerHTML = `
      <option value="days">dagar</option>
      <option value="weeks">veckor</option>
      <option value="months">månader</option>
    `;
    unitSelect.value = hasRecurrence ? item.recurrence.unit : "weeks";
    unitSelect.disabled = !hasRecurrence;
    row.appendChild(unitSelect);

    enabledCb.addEventListener("change", () => {
      intervalInput.disabled = !enabledCb.checked;
      unitSelect.disabled = !enabledCb.checked;
    });

    const saveBtn = document.createElement("button");
    saveBtn.className = "secondary";
    saveBtn.textContent = "Spara";
    saveBtn.addEventListener("click", async () => {
      const recurrence = enabledCb.checked
        ? { interval: Math.max(1, parseInt(intervalInput.value, 10) || 1), unit: unitSelect.value }
        : null;
      await this._hass.callWS({
        type: "family_todo/set_item_extra",
        entry_id: list.entry_id,
        uid: item.uid,
        recurrence,
      });
      await this._reloadItems(list.entry_id);
      this._render();
    });
    row.appendChild(saveBtn);

    return row;
  }

  _renderDueEditor(list, item) {
    const row = document.createElement("div");
    row.className = "ft-row";
    row.innerHTML = `<span>Förfaller:</span>`;

    const [datePart, timePart] = item.due ? item.due.split("T") : ["", ""];
    const dateInput = document.createElement("input");
    dateInput.type = "date";
    dateInput.value = datePart || "";
    row.appendChild(dateInput);

    const timeInput = document.createElement("input");
    timeInput.type = "time";
    timeInput.value = timePart ? timePart.slice(0, 5) : "";
    timeInput.title = "Valfritt - sätt en tid för att få en påminnelse skickad om uppgiften "
      + "fortfarande inte är avbockad då (se Notiser-tabben)";
    row.appendChild(timeInput);

    const saveBtn = document.createElement("button");
    saveBtn.className = "secondary";
    saveBtn.textContent = "Spara";
    saveBtn.addEventListener("click", async () => {
      const date = dateInput.value;
      const due = date ? (timeInput.value ? `${date}T${timeInput.value}` : date) : null;
      await this._hass.callWS({
        type: "family_todo/update_item",
        entry_id: list.entry_id,
        uid: item.uid,
        summary: item.summary,
        status: item.status,
        description: item.description,
        due,
      });
      await this._reloadItems(list.entry_id);
      this._render();
    });
    row.appendChild(saveBtn);

    return row;
  }

  _renderItemDetail(list, item) {
    const detail = document.createElement("div");
    detail.className = "ft-item-detail";

    const sections = this._sections[list.entry_id] || [];
    if (sections.length) {
      const sectionRow = document.createElement("div");
      sectionRow.className = "ft-row";
      const sectionSelect = document.createElement("select");
      sectionSelect.innerHTML =
        `<option value="">Ingen sektion</option>` +
        sections.map((s) => `<option value="${_esc(s.id)}">${_esc(s.name)}</option>`).join("");
      sectionSelect.value = item.section_id || "";
      sectionSelect.addEventListener("change", async () => {
        await this._hass.callWS({
          type: "family_todo/set_item_extra",
          entry_id: list.entry_id,
          uid: item.uid,
          section_id: sectionSelect.value || null,
        });
        await this._reloadItems(list.entry_id);
        this._render();
      });
      sectionRow.innerHTML = `<span>Sektion:</span>`;
      sectionRow.appendChild(sectionSelect);
      detail.appendChild(sectionRow);
    }

    detail.appendChild(this._renderDueEditor(list, item));

    const assigneeRow = document.createElement("div");
    assigneeRow.className = "ft-row";
    const select = document.createElement("select");
    select.innerHTML = `<option value="">Ingen tilldelad</option>` +
      this._persons.map((p) => `<option value="${_esc(p.name)}">${_esc(p.name)}</option>`).join("") +
      `<option value="__custom__">Annat namn...</option>`;
    const currentIsPerson = this._persons.some((p) => p.name === item.assignee);
    if (item.assignee && !currentIsPerson) {
      select.innerHTML += `<option value="${_esc(item.assignee)}" selected>${_esc(item.assignee)}</option>`;
    } else {
      select.value = item.assignee || "";
    }
    select.addEventListener("change", async () => {
      let assignee = select.value;
      if (assignee === "__custom__") {
        assignee = prompt("Namn:", "") || "";
      }
      await this._hass.callWS({
        type: "family_todo/set_item_extra",
        entry_id: list.entry_id,
        uid: item.uid,
        assignee,
      });
      await this._reloadItems(list.entry_id);
      this._render();
    });
    assigneeRow.innerHTML = `<span>Tilldelad:</span>`;
    assigneeRow.appendChild(select);
    detail.appendChild(assigneeRow);

    detail.appendChild(this._renderRecurrenceEditor(list, item));

    const subtasksTitle = document.createElement("div");
    subtasksTitle.className = "ft-row";
    subtasksTitle.innerHTML = `<span>Delsteg:</span>`;
    detail.appendChild(subtasksTitle);

    const saveSubtasks = async (subtasks) => {
      await this._hass.callWS({
        type: "family_todo/set_item_extra",
        entry_id: list.entry_id,
        uid: item.uid,
        subtasks,
      });
      await this._reloadItems(list.entry_id);
      this._render();
    };

    for (const sub of item.subtasks) {
      const subRow = document.createElement("div");
      subRow.className = "ft-subtask-row";
      const subCheckbox = document.createElement("input");
      subCheckbox.type = "checkbox";
      subCheckbox.checked = sub.complete;
      subCheckbox.addEventListener("change", () => {
        const updated = item.subtasks.map((s) =>
          s.id === sub.id ? { ...s, complete: subCheckbox.checked } : s
        );
        saveSubtasks(updated);
      });
      subRow.appendChild(subCheckbox);
      const subText = document.createElement("span");
      subText.className = sub.complete ? "done" : "";
      subText.textContent = sub.summary;
      subRow.appendChild(subText);
      const subDelete = document.createElement("button");
      subDelete.className = "text";
      subDelete.innerHTML = `<ha-icon icon="mdi:close"></ha-icon>`;
      subDelete.addEventListener("click", () => {
        saveSubtasks(item.subtasks.filter((s) => s.id !== sub.id));
      });
      subRow.appendChild(subDelete);
      detail.appendChild(subRow);
    }

    const addSubRow = document.createElement("div");
    addSubRow.className = "ft-row";
    addSubRow.innerHTML = `<input type="text" placeholder="Nytt delsteg..." />`;
    const addSubInput = addSubRow.querySelector("input");
    const addSubBtn = document.createElement("button");
    addSubBtn.className = "secondary";
    addSubBtn.textContent = "Lägg till";
    const doAddSub = () => {
      const summary = addSubInput.value.trim();
      if (!summary) return;
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      saveSubtasks([...item.subtasks, { id, summary, complete: false }]);
    };
    addSubBtn.addEventListener("click", doAddSub);
    addSubInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") doAddSub();
    });
    addSubRow.appendChild(addSubBtn);
    detail.appendChild(addSubRow);

    return detail;
  }
}

function _hasDueTime(due) {
  // "YYYY-MM-DD" (datum utan tid) är 10 tecken - allt längre har en klockslagsdel.
  // Måste matcha reminders.py:_due_datetime på backend.
  return !!due && due.length > 10;
}

function _formatDue(due) {
  if (!due) return "";
  const hasTime = _hasDueTime(due);
  const d = new Date(hasTime ? due : `${due}T00:00`);
  if (isNaN(d.getTime())) return due;
  const datePart = d.toLocaleDateString("sv-SE");
  if (!hasTime) return datePart;
  return `${datePart} ${d.toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" })}`;
}

function _esc(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

const _RECURRENCE_UNIT_WORDS = { days: "dag", weeks: "vecka", months: "månad" };

function _recurrenceLabel(recurrence) {
  if (!recurrence) return "";
  const word = _RECURRENCE_UNIT_WORDS[recurrence.unit] || recurrence.unit;
  if (recurrence.interval === 1) return `Varje ${word}`;
  if (recurrence.interval === 2) return `Varannan ${word}`;
  return `Var ${recurrence.interval}:e ${word}`;
}

customElements.define("family-todo-panel", FamilyTodoPanel);
