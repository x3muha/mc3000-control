"use strict";

(() => {
  const translations = new Map(Object.entries({
    "LADEGERÄTE": "CHARGERS",
    "Ladegeräte": "Chargers",
    "Profile": "Profiles",
    "Batterien": "Batteries",
    "Aufzeichnungen": "Recordings",
    "Verlauf": "History",
    "Einstellungen": "Settings",
    "Meldungen": "Notifications",
    "Ladegeräte verbinden": "Connect chargers",
    "BLUETOOTH": "BLUETOOTH",
    "Noch kein Ladegerät eingerichtet": "No charger configured yet",
    "Geräte suchen": "Find chargers",
    "PROFILBIBLIOTHEK": "PROFILE LIBRARY",
    "Ladeprofile": "Charging profiles",
    "Neues Profil": "New profile",
    "Alle Profile": "All profiles",
    "Eigene Profile": "Custom profiles",
    "Automatic profiles": "Automatic profiles",
    "Automatikprofile": "Automatic profiles",
    "Lithium profiles": "Lithium profiles",
    "Lithium-Profile": "Lithium profiles",
    "Allgemein": "General",
    "Alle Automatikprogramme und gespeicherten Profile.": "All automatic and saved profiles.",
    "Selbst angelegte und duplizierte Profile.": "Profiles created or duplicated by the user.",
    "Profile exportieren": "Export profiles",
    "Profile importieren": "Import profiles",
    "Name": "Name",
    "Kategorie": "Category",
    "Akkutyp": "Battery type",
    "Programm": "Program",
    "Ladestrom": "Charge current",
    "Endspannung": "End voltage",
    "Mitgeliefertes Profil": "Built-in profile",
    "Eigenes Profil": "Custom profile",
    "Mitgeliefertes Automatikprofil · Strom nach Kapazität": "Built-in automatic profile · current by capacity",
    "Eigenes Automatikprofil · Strom nach Kapazität": "Custom automatic profile · current by capacity",
    "Nach Akkutyp": "By battery type",
    "Bei Slot wählen": "Select for slot",
    "LANGZEITARCHIV": "LONG-TERM ARCHIVE",
    "Batteriemanager": "Battery manager",
    "Archiv öffnen": "Open archive",
    "Zellkatalog": "Cell catalog",
    "Neue Batterie": "New battery",
    "Zellen-Sortierer / Pack-Builder": "Cell sorter / pack builder",
    "Getestete Zellen nach Kapazität und Innenwiderstand gruppieren": "Group tested cells by capacity and internal resistance",
    "Zellen pro Gruppe": "Cells per group",
    "Anzahl Gruppen": "Number of groups",
    "Max. Kapazitätsabweichung": "Max. capacity spread",
    "Max. Widerstandsabweichung": "Max. resistance spread",
    "Passende Gruppen berechnen": "Calculate matching groups",
    "Batterienummer": "Battery number",
    "Öffnen": "Open",
    "BATTERIEAKTE": "BATTERY RECORD",
    "Batterie auswählen oder neu anlegen": "Select or create a battery",
    "QR-Etikett": "QR label",
    "Steckblatt PDF": "Data sheet PDF",
    "CSV exportieren": "Export CSV",
    "Bearbeiten": "Edit",
    "Standardprogramm": "Default program",
    "Archivieren": "Archive",
    "Endgültig löschen": "Delete permanently",
    "VERGLEICH": "COMPARISON",
    "Lade- und Entladekurven": "Charge and discharge curves",
    "Messwert": "Metric",
    "Spannung": "Voltage",
    "Strom": "Current",
    "Kapazität": "Capacity",
    "Temperatur": "Temperature",
    "Innenwiderstand": "Internal resistance",
    "Auswahl vergleichen": "Compare selection",
    "Zoom zurücksetzen": "Reset zoom",
    "Laden": "Charge",
    "Pause": "Pause",
    "Entladen": "Discharge",
    "Außerhalb eines Programms": "Outside a program",
    "HISTORIE": "HISTORY",
    "Gespeicherte Programmläufe": "Saved program runs",
    "Bis zu 5 Läufe auswählen": "Select up to 5 runs",
    "Beginn": "Start",
    "Gerät / Slot": "Charger / slot",
    "Soll / Ist": "Target / actual",
    "ZEITREIHEN": "TIME SERIES",
    "Aktualisieren": "Refresh",
    "Ladegerät": "Charger",
    "Slot": "Slot",
    "Zeitraum": "Time range",
    "Letzte Stunde": "Last hour",
    "Letzte 6 Stunden": "Last 6 hours",
    "Letzte 24 Stunden": "Last 24 hours",
    "Letzte 7 Tage": "Last 7 days",
    "Letzte 30 Tage": "Last 30 days",
    "Noch keine Daten geladen": "No data loaded yet",
    "Spannung und Strom": "Voltage and current",
    "Temperatur und Innenwiderstand": "Temperature and internal resistance",
    "PROGRAMMLÄUFE": "PROGRAM RUNS",
    "Letzte Lade- und Entladevorgänge": "Latest charge and discharge runs",
    "Gerät": "Charger",
    "Dauer": "Duration",
    "Max. Temperatur": "Max. temperature",
    "VERHALTEN": "BEHAVIOR",
    "Darstellung": "Appearance",
    "Farbschema": "Color scheme",
    "Systemeinstellung verwenden": "Use system setting",
    "Hell": "Light",
    "Dunkel": "Dark",
    "Sprache": "Language",
    "Deutsch": "German",
    "Englisch": "English",
    "Vorauswahl für neue Slots": "Default for new slots",
    "Vorgeschlagenes Programm": "Suggested program",
    "Diagrammfarben": "Chart colors",
    "Deckkraft der Phasenflächen": "Phase area opacity",
    "Seitenschutz": "Access protection",
    "Login aktivieren": "Enable login",
    "Benutzername": "Username",
    "Passwort": "Password",
    "Jetzt abmelden": "Log out now",
    "Diese Oberfläche ist geschützt. Bitte anmelden.": "This interface is protected. Please sign in.",
    "Anmelden": "Sign in",
    "Anmeldung fehlgeschlagen": "Sign-in failed",
    "Einstellungen speichern": "Save settings",
    "Datensicherung": "Backup",
    "Backup herunterladen": "Download backup",
    "Backup wiederherstellen": "Restore backup",
    "Diagnosepaket herunterladen": "Download diagnostics",
    "App installieren": "Install app",
    "AKTUELLE VERSION": "CURRENT VERSION",
    "Version": "Version",
    "Versionsinformationen werden geladen...": "Loading version information...",
    "Verbindungsmanager": "Connection manager",
    "Eingerichtete Ladegeräte": "Configured chargers",
    "Verfügbare Ladegeräte": "Available chargers",
    "Neu suchen": "Search again",
    "Schließen": "Close",
    "Abbrechen": "Cancel",
    "Speichern": "Save",
    "Gerätedaten bearbeiten": "Edit charger details",
    "Seriennummer (optional)": "Serial number (optional)",
    "Programm und Batterie": "Program and battery",
    "Batterieakte (optional)": "Battery record (optional)",
    "Zeitlimit": "Time limit",
    "Automatisch": "Automatic",
    "Manuell": "Manual",
    "Aus": "Off",
    "Manuelles Zeitlimit": "Manual time limit",
    "Für Slot übernehmen": "Apply to slot",
    "Programme vorbereiten": "Prepare programs",
    "Programm für alle Slots": "Program for all slots",
    "Programme übernehmen": "Apply programs",
    "SPANNUNGSVERLAUF": "VOLTAGE CURVE",
    "Lade Daten...": "Loading data...",
    "PROFIL": "PROFILE",
    "Ladeprofil erstellen": "Create charging profile",
    "Beschreibung": "Description",
    "Lade-Endspannung": "Charge end voltage",
    "Entlade-Endspannung": "Discharge end voltage",
    "Lade-Abschaltstrom": "Charge cutoff current",
    "Entlade-Abschaltstrom": "Discharge cutoff current",
    "Ladepause": "Charge rest",
    "Entladepause": "Discharge rest",
    "Zykluszahl": "Cycle count",
    "Zyklusfolge": "Cycle order",
    "Temperaturlimit": "Temperature limit",
    "Profil speichern": "Save profile",
    "Batterie anlegen": "Create battery",
    "LOKALER ZELLKATALOG": "LOCAL CELL CATALOG",
    "Katalogquellen einlesen": "Import catalog sources",
    "Noch kein lokaler Katalog vorhanden.": "No local catalog yet.",
    "Kein automatischer Abgleich. Vorhandene Katalogdaten bleiben bei einem Quellenfehler erhalten.": "No automatic synchronization. Existing catalog data is retained when a source fails.",
    "Ausgewählte Quellen einlesen": "Import selected sources",
    "Zellmodell im lokalen Katalog": "Cell model in local catalog",
    "Suchen": "Search",
    "Übernehmen": "Apply",
    "Erweiterte technische Daten": "Extended technical data",
    "Chemiedetail": "Chemistry detail",
    "Gewicht": "Weight",
    "Nennspannung": "Nominal voltage",
    "Minimale Spannung": "Minimum voltage",
    "Maximale Spannung": "Maximum voltage",
    "Maximaler Ladestrom": "Maximum charge current",
    "Maximaler Entladestrom": "Maximum discharge current",
    "Zyklenlebensdauer": "Cycle life",
    "Herstellungsjahr": "Manufacture year",
    "Abmessungen": "Dimensions",
    "Datenquelle": "Data source",
    "Link zum Datensatz": "Link to dataset record",
    "Technische Zusatzangaben": "Additional technical data",
    "Hersteller": "Manufacturer",
    "Modell": "Model",
    "Bauform": "Form factor",
    "Herkunft": "Origin",
    "Notizen": "Notes",
    "MELDUNGEN": "NOTIFICATIONS",
    "Abgeschlossene Programme": "Completed programs",
    "Browser-Meldungen aktivieren": "Enable browser notifications",
    "Als gelesen markieren": "Mark as read",
    "Keine Ladegeräte eingerichtet": "No chargers configured",
    "Keine Daten": "No data",
    "Kein Programm gewählt": "No program selected",
    "Keine Batterie zugeordnet": "No battery assigned",
    "Programm wählen": "Select program",
    "Batteriedaten": "Battery details",
    "Alle Programme": "All programs",
    "Alle starten": "Start all",
    "Alles stoppen": "Stop all",
    "Verbunden": "Connected",
    "Bereit": "Ready",
    "Fertig": "Finished",
    "Keine Fix-Hinweise hinterlegt.": "No release notes available.",
    "Bericht": "Report",
    "Diagramm": "Chart",
    "Löschen": "Delete",
    "Duplizieren": "Duplicate",
    "Anwenden": "Apply",
  }));
  const originalText = new WeakMap();
  const originalAttributes = new WeakMap();
  let language = "de";
  try {
    language = localStorage.getItem("mc3000-language") === "en" ? "en" : "de";
  } catch (_error) {
    // German remains the default if persistent browser storage is unavailable.
  }

  function english(value) {
    const exact = translations.get(value);
    if (exact) return exact;
    let match = value.match(/^(\d+) von (\d+) Ladegeräten verbunden$/);
    if (match) return `${match[1]} of ${match[2]} chargers connected`;
    match = value.match(/^Stand (.+)$/);
    if (match) return `Updated ${match[1]}`;
    match = value.match(/^Batterie (.+)$/);
    if (match) return `Battery ${match[1]}`;
    match = value.match(/^(\d+) Punkte · Intervall (.+)$/);
    if (match) return `${match[1]} points · interval ${match[2]}`;
    match = value.match(/^Zeitlimit manuell · (.+) Std\.$/);
    if (match) return `Manual time limit · ${match[1]} h`;
    match = value.match(/^Zeitlimit automatisch · (.+) Std\.$/);
    if (match) return `Automatic time limit · ${match[1]} h`;
    match = value.match(/^(.+) C Laden$/);
    if (match) return `${match[1]} C charge`;
    match = value.match(/^(.+) C Entladen$/);
    if (match) return `${match[1]} C discharge`;
    return value;
  }

  function translateTextNode(node) {
    if (!node.nodeValue || !node.nodeValue.trim()) return;
    const current = node.nodeValue.trim();
    const stored = originalText.get(node);
    if (language === "de") {
      if (stored) node.nodeValue = node.nodeValue.replace(current, stored);
      return;
    }
    const source = stored && english(stored) === current ? stored : current;
    originalText.set(node, source);
    const translated = english(source);
    if (translated !== current) node.nodeValue = node.nodeValue.replace(current, translated);
  }

  function translateElement(element) {
    for (const name of ["title", "aria-label", "placeholder"]) {
      if (!element.hasAttribute?.(name)) continue;
      let stored = originalAttributes.get(element) || {};
      const current = element.getAttribute(name);
      if (language === "de") {
        if (stored[name]) element.setAttribute(name, stored[name]);
      } else {
        const source = stored[name] && english(stored[name]) === current ? stored[name] : current;
        stored = { ...stored, [name]: source };
        originalAttributes.set(element, stored);
        element.setAttribute(name, english(source));
      }
    }
  }

  function translateTree(root = document.body) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) translateTextNode(root);
    if (root.nodeType === Node.ELEMENT_NODE) translateElement(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      if (walker.currentNode.nodeType === Node.TEXT_NODE) translateTextNode(walker.currentNode);
      else translateElement(walker.currentNode);
    }
  }

  function setLanguage(value) {
    language = value === "en" ? "en" : "de";
    try {
      localStorage.setItem("mc3000-language", language);
    } catch (_error) {
      // The selected language remains active for the current page.
    }
    document.documentElement.lang = language;
    const select = document.getElementById("settingsLanguage");
    if (select) select.value = language;
    translateTree();
  }

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === "characterData") translateTextNode(mutation.target);
      for (const node of mutation.addedNodes) translateTree(node);
    }
  });
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  document.addEventListener("change", (event) => {
    if (event.target?.id === "settingsLanguage") setLanguage(event.target.value);
  });
  window.MC3000_I18N = { setLanguage, get language() { return language; } };
  setLanguage(language);
})();
