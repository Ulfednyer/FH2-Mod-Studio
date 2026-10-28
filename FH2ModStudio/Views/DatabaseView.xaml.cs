using System.Data;
using System.Globalization;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;
using FH2ModStudio.Core;

namespace FH2ModStudio.Views;

public sealed class TableEntry
{
    public string Name { get; init; } = "";
    public string Sql { get; init; } = "";
    public string Hint { get; set; } = "";
}

public partial class DatabaseView : UserControl
{
    // rows are fetched a page at a time while scrolling (the game answers each query over a pipe; 500 rows x 60
    // columns at once made the page freeze)
    private const int PageSize = 200;
    private const string TextSuffix = " ▸ text";
    private long _browseTotal;
    private int _browseToken;
    private bool _loadingMore;
    private DataTable? _browseTable;
    private string _browseSelect = "";
    private readonly Dictionary<string, Dictionary<int, string>> _stringCache = new(StringComparer.OrdinalIgnoreCase);
    private Dictionary<string, double> _colWidths = new();
    private MainWindow _main = null!;
    private SessionStatus _status = new(GameState.NotRunning, false, false, 0, null);
    private List<TableEntry> _tables = new();
    private string? _table;
    private bool _browseEditable;
    private SqlResult? _browseResult;

    public DatabaseView()
    {
        InitializeComponent();
        BrowseGrid.AddHandler(ScrollViewer.ScrollChangedEvent, new ScrollChangedEventHandler(BrowseGrid_ScrollChanged));
    }

    private SqlPipe Sql => _main.Session.Sql;
    private DbHistory History => _main.Session.History;

    public void Init(MainWindow main)
    {
        _main = main;
        foreach (var t in new[] { "Insert a template…", "Show rows of the current table", "Multiply a column", "Set a value for matching rows",
                                  "Find tables containing a column", "List all tables" })
            TemplateCombo.Items.Add(new ComboBoxItem { Content = t });
        TemplateCombo.SelectedIndex = 0;
        RefreshMods();
        RefreshHistory();
    }

    public void OnShown()
    {
        if (_status.DatabaseReady && _tables.Count == 0) _ = LoadTablesAsync();
    }

    private void GoCars_Click(object sender, RoutedEventArgs e) => _main.ShowPage("cars");

    public void OnStatus(SessionStatus s)
    {
        bool wasReady = _status.DatabaseReady;
        _status = s;
        OfflinePanel.Visibility = s.DatabaseReady ? Visibility.Collapsed : Visibility.Visible;
        TableList.Visibility = s.DatabaseReady ? Visibility.Visible : Visibility.Hidden;
        // offline: no search box behind the card and a clearly inactive workspace instead of an empty grey grid
        ((FrameworkElement)SearchBox.Parent).Visibility = s.DatabaseReady ? Visibility.Visible : Visibility.Hidden;
        Workspace.IsEnabled = s.DatabaseReady;
        Workspace.Opacity = s.DatabaseReady ? 1 : 0.35;
        OfflineTxt.Text = s.Game switch
        {
            GameState.NotRunning => "The game isn't running. Launch it from the Home page - the database becomes available once you're in the game world.",
            GameState.Launcher => "Start the game in Azimuth. The database becomes available once the game has loaded.",
            _ when !s.ModsLoaded => "Mods aren't loaded into this game session. Use 'Load mods now' on the Home page.",
            _ => "Waiting for the game to finish loading its database…",
        };
        if (s.DatabaseReady && !wasReady)
        {
            _tables.Clear();
            if (IsVisible) _ = LoadTablesAsync();
        }
    }

    // ───────────── tables ─────────────

    private async Task LoadTablesAsync()
    {
        var r = await Sql.ExecuteAsync("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name;");
        if (!r.Ok || r.Results.Count == 0) { _main.SetStatus("Could not list tables: " + r.Error); return; }
        _tables = r.Results[0].Rows.Select(row => new TableEntry { Name = row[0] ?? "", Sql = row[1] ?? "" }).ToList();
        TableCountTxt.Text = $"{_tables.Count}";
        ApplySearch();
    }

    private void SearchBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        SearchHint.Visibility = SearchBox.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
        ApplySearch();
    }

    private void ApplySearch()
    {
        var term = SearchBox.Text.Trim();
        if (term.Length == 0)
        {
            foreach (var t in _tables) t.Hint = "";
            TableList.ItemsSource = _tables.ToList();
            return;
        }
        var list = new List<TableEntry>();
        foreach (var t in _tables)
        {
            if (t.Name.Contains(term, StringComparison.OrdinalIgnoreCase)) { t.Hint = ""; list.Add(t); continue; }
            var col = Regex.Matches(t.Sql, @"\[?(\w+)\]?\s+(?:INT|INTEGER|REAL|TEXT|NUMERIC|BLOB|FLOAT|BOOL)", RegexOptions.IgnoreCase)
                .Select(m => m.Groups[1].Value).FirstOrDefault(c => c.Contains(term, StringComparison.OrdinalIgnoreCase));
            if (col != null) { t.Hint = "column: " + col; list.Add(t); }
        }
        TableList.ItemsSource = list;
    }

    private void TableList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (TableList.SelectedItem is not TableEntry t) return;
        _table = t.Name;
        FilterBox.Text = "";
        BrowseSeg.IsChecked = true;
        _ = LoadBrowseAsync();
    }

    private string WhereClause => string.IsNullOrWhiteSpace(FilterBox.Text) ? "" : " WHERE " + FilterBox.Text.Trim().TrimEnd(';');

    private async Task LoadBrowseAsync()
    {
        if (_table == null) return;
        int token = ++_browseToken;
        var q = DbHistory.QuoteIdent(_table);
        TableTitle.Text = _table;
        var count = await Sql.ExecuteAsync($"SELECT COUNT(*) FROM {q}{WhereClause};");
        _browseSelect = $"SELECT rowid AS __rowid, * FROM {q}{WhereClause} ORDER BY rowid";
        var r = await Sql.ExecuteAsync($"{_browseSelect} LIMIT {PageSize};");
        _browseEditable = r.Ok;
        if (!r.Ok)
        {
            _browseSelect = $"SELECT * FROM {q}{WhereClause}";
            r = await Sql.ExecuteAsync($"{_browseSelect} LIMIT {PageSize};");
        }
        if (token != _browseToken) return;
        if (!r.Ok || r.Results.Count == 0)
        {
            RowCountTxt.Text = "";
            BrowseGrid.ItemsSource = null;
            _browseTable = null;
            _main.SetStatus("Query failed: " + r.Error);
            return;
        }
        _browseResult = r.Results[0];
        _browseTotal = count.Ok && count.Results.Count > 0 && long.TryParse(count.Results[0].Rows[0][0], out var n) ? n : _browseResult.Rows.Count;
        _browseTable = NewBrowseTable(_browseResult);
        AppendRows(_browseResult);
        BrowseGrid.IsReadOnly = !_browseEditable;
        BrowseGrid.ItemsSource = _browseTable.DefaultView;
        UpdateRowCount();
        FillScaleColumns();
        _main.SetStatus(_browseEditable ? $"{_table}: double-click a cell to edit it in the game." : $"{_table} loaded.");
    }

    private void UpdateRowCount()
    {
        int shown = _browseTable?.Rows.Count ?? 0;
        RowCountTxt.Text = shown < _browseTotal ? $"{shown} of {_browseTotal} rows · more load as you scroll" : $"{_browseTotal} rows";
        if (!_browseEditable) RowCountTxt.Text += " · read-only (table has no row ids)";
    }

    private void BrowseGrid_ScrollChanged(object sender, ScrollChangedEventArgs e)
    {
        // next page once the last ~40 rows come into view
        if (e.VerticalChange <= 0 && e.ExtentHeightChange == 0) return;
        if (e.VerticalOffset + e.ViewportHeight >= e.ExtentHeight - 40) _ = LoadMoreAsync();
    }

    private async Task LoadMoreAsync()
    {
        if (_loadingMore || _browseTable == null || _browseTable.Rows.Count >= _browseTotal) return;
        _loadingMore = true;
        int token = _browseToken;
        try
        {
            var r = await Sql.ExecuteAsync($"{_browseSelect} LIMIT {PageSize} OFFSET {_browseTable.Rows.Count};");
            if (token != _browseToken || !r.Ok || r.Results.Count == 0) return;
            AppendRows(r.Results[0]);
            UpdateRowCount();
        }
        finally
        {
            _loadingMore = false;
        }
    }

    /// <summary>Columns of the query plus, after each column holding string ids ("_&amp;3444639744"), a read-only
    /// column with the text from the table's string table. Column widths come from the first page.</summary>
    private DataTable NewBrowseTable(SqlResult first)
    {
        var strings = Strings(_table!);
        var dt = new DataTable();
        var names = new HashSet<string>();
        _colWidths = new Dictionary<string, double>();
        for (int i = 0; i < first.Columns.Count; i++)
        {
            var c = first.Columns[i];
            var name = c;
            for (int k = 2; !names.Add(name); k++) name = $"{c} ({k})";
            dt.Columns.Add(name, typeof(string));
            int len = Math.Max(name.Length, first.Rows.Select(row => row[i]?.Length ?? 4).DefaultIfEmpty(4).Max());
            _colWidths[name] = Math.Clamp(len * 7 + 18, 48, 320);
            if (strings.Count > 0 && first.Rows.Any(row => row[i] is { } v && v.StartsWith("_&", StringComparison.Ordinal)))
            {
                var textCol = dt.Columns.Add(name + TextSuffix, typeof(string));
                textCol.ExtendedProperties["source"] = i;
                int tlen = first.Rows.Select(row => StringTables.Text(strings, row[i])?.Length ?? 0).DefaultIfEmpty(0).Max();
                _colWidths[textCol.ColumnName] = Math.Clamp(Math.Max(tlen, textCol.ColumnName.Length) * 7 + 18, 60, 320);
            }
        }
        return dt;
    }

    private void AppendRows(SqlResult page)
    {
        if (_browseTable == null) return;
        var strings = Strings(_table!);
        _browseTable.BeginLoadData();
        foreach (var row in page.Rows)
        {
            var values = new object[_browseTable.Columns.Count];
            for (int c = 0, src = 0; c < values.Length; c++)
            {
                var col = _browseTable.Columns[c];
                if (col.ExtendedProperties["source"] is int from)
                    values[c] = (object?)StringTables.Text(strings, row[from]) ?? DBNull.Value;
                else
                    values[c] = (object?)row[src++] ?? DBNull.Value;
            }
            _browseTable.Rows.Add(values);
        }
        _browseTable.EndLoadData();
    }

    private Dictionary<int, string> Strings(string table)
    {
        if (!_stringCache.TryGetValue(table, out var d))
            _stringCache[table] = d = StringTables.Load(_main.Settings.MediaDir, table);
        return d;
    }

    private static DataTable ToDataTable(SqlResult r)
    {
        var dt = new DataTable();
        var names = new HashSet<string>();
        foreach (var c in r.Columns)
        {
            var name = c;
            for (int i = 2; !names.Add(name); i++) name = $"{c} ({i})";
            dt.Columns.Add(name, typeof(string));
        }
        dt.BeginLoadData();
        foreach (var row in r.Rows) dt.Rows.Add(row.Select(v => (object?)v ?? DBNull.Value).ToArray());
        dt.EndLoadData();
        return dt;
    }

    private void Grid_AutoGeneratingColumn(object? sender, DataGridAutoGeneratingColumnEventArgs e)
    {
        if (e.PropertyName == "__rowid") { e.Cancel = true; return; }
        e.Column.Header = e.PropertyName;
        if (sender == BrowseGrid && _colWidths.TryGetValue(e.PropertyName, out var w)) e.Column.Width = new DataGridLength(w);
        if (e.PropertyName.EndsWith(TextSuffix, StringComparison.Ordinal))
        {
            e.Column.IsReadOnly = true;   // shown from the string tables; edit the id column next to it
        }
        if (e.Column is DataGridBoundColumn bound)
            bound.Binding = new Binding("[" + e.PropertyName + "]") { TargetNullValue = "NULL" };
    }

    private async void BrowseGrid_CellEditEnding(object? sender, DataGridCellEditEndingEventArgs e)
    {
        if (e.EditAction != DataGridEditAction.Commit || _table == null || !_browseEditable) return;
        if (e.Row.Item is not DataRowView view || e.EditingElement is not TextBox box) return;
        var column = (string)e.Column.Header;
        var oldValue = view.Row[column] as string;
        var newText = box.Text;
        string? newValue = newText.Equals("NULL", StringComparison.OrdinalIgnoreCase) ? null : newText;
        if (newValue == oldValue) return;
        var rowid = view.Row["__rowid"] as string;
        var sql = $"UPDATE {DbHistory.QuoteIdent(_table)} SET {DbHistory.QuoteIdent(column)} = {DbHistory.Literal(newValue)} WHERE rowid = {rowid};";
        var desc = $"{_table}.{column}: {oldValue ?? "NULL"} → {newValue ?? "NULL"}";
        var warnings = new List<string>();
        var r = await Task.Run(() => History.Run(sql, desc, warnings));
        if (!r.Ok)
        {
            view.Row[column] = (object?)oldValue ?? DBNull.Value;
            _main.SetStatus("Edit rejected by the game: " + r.Error);
            return;
        }
        RefreshHistory();
        _main.SetStatus($"Changed {desc} (live). Undo it under History & saved mods.");
    }

    private void FilterBox_TextChanged(object sender, TextChangedEventArgs e) =>
        FilterHint.Visibility = FilterBox.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;

    private void FilterBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) _ = LoadBrowseAsync();
    }

    private void ApplyFilter_Click(object sender, RoutedEventArgs e) => _ = LoadBrowseAsync();
    private void Refresh_Click(object sender, RoutedEventArgs e) => _ = LoadBrowseAsync();

    // ───────────── scale helper ─────────────

    private void ScaleToggle_Click(object sender, RoutedEventArgs e)
    {
        bool show = ScalePanel.Visibility != Visibility.Visible;
        ScalePanel.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
        ScaleToggleBtn.Content = show ? "Scale a column ▴" : "Scale a column ▾";
        if (show) _ = UpdateScalePreviewAsync();
    }

    private void FillScaleColumns()
    {
        ScaleColumnCombo.Items.Clear();
        if (_browseResult == null) return;
        for (int i = 0; i < _browseResult.Columns.Count; i++)
        {
            var name = _browseResult.Columns[i];
            // keys and yes/no flags would break the data if multiplied, so they are never offered
            if (name == "__rowid" || Regex.IsMatch(name, @"(^Id$|ID$|Id$|^Is[A-Z])")) continue;
            var values = _browseResult.Rows.Select(r => r[i]).Where(v => v != null).ToList();
            if (values.Count > 0 && values.All(v => double.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out _)))
                ScaleColumnCombo.Items.Add(new ComboBoxItem { Content = name, Tag = name });
        }
        if (ScaleColumnCombo.Items.Count > 0) ScaleColumnCombo.SelectedIndex = 0;
        _ = UpdateScalePreviewAsync();
    }

    private void ScaleInput_Changed(object sender, RoutedEventArgs e) => _ = UpdateScalePreviewAsync();

    private bool TryScaleInputs(out string column, out double factor)
    {
        column = (ScaleColumnCombo.SelectedItem as ComboBoxItem)?.Tag as string ?? "";
        bool ok = double.TryParse(ScaleFactorBox.Text.Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out factor);
        return ok && column.Length > 0 && _table != null;
    }

    private async Task UpdateScalePreviewAsync()
    {
        if (ScalePanel.Visibility != Visibility.Visible) return;
        if (!TryScaleInputs(out var column, out var factor))
        {
            ScalePreviewTxt.Text = ScaleColumnCombo.Items.Count == 0 ? "This table has no number columns." : "Enter a number to multiply by.";
            ScaleApplyBtn.IsEnabled = false;
            return;
        }
        var q = DbHistory.QuoteIdent(column);
        var r = await Sql.ExecuteAsync($"SELECT COUNT({q}), MIN({q}), MAX({q}) FROM {DbHistory.QuoteIdent(_table!)}{WhereClause};");
        if (!r.Ok || r.Results.Count == 0) { ScalePreviewTxt.Text = r.Error ?? ""; ScaleApplyBtn.IsEnabled = false; return; }
        var row = r.Results[0].Rows[0];
        string Fmt(string? v, double f) => double.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out var d)
            ? (d * f).ToString("0.####", CultureInfo.InvariantCulture) : "-";
        ScalePreviewTxt.Text = $"Changes {row[0]} row(s){(WhereClause.Length > 0 ? " matching the filter" : "")}: " +
                               $"range {Fmt(row[1], 1)}…{Fmt(row[2], 1)}  →  {Fmt(row[1], factor)}…{Fmt(row[2], factor)}";
        ScaleApplyBtn.IsEnabled = row[0] != "0";
    }

    private async void ScaleApply_Click(object sender, RoutedEventArgs e)
    {
        if (!TryScaleInputs(out var column, out var factor)) return;
        var q = DbHistory.QuoteIdent(column);
        var f = factor.ToString(CultureInfo.InvariantCulture);
        var sql = $"UPDATE {DbHistory.QuoteIdent(_table!)} SET {q} = {q} * {f}{WhereClause};";
        var desc = $"Scale {_table}.{column} ×{f}{(WhereClause.Length > 0 ? " (filtered)" : "")}";
        var warnings = new List<string>();
        var r = await Task.Run(() => History.Run(sql, desc, warnings));
        RefreshHistory();
        _main.SetStatus(r.Ok
            ? $"{desc} applied live.{(warnings.Count > 0 ? " Note: " + warnings[0] : " Undo or save it as a mod under History & saved mods.")}"
            : "Failed: " + r.Error);
        await LoadBrowseAsync();
    }

    // ───────────── SQL console ─────────────

    private void SqlEditor_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && Keyboard.Modifiers == ModifierKeys.Control)
        {
            e.Handled = true;
            RunSql_Click(sender, e);
        }
    }

    private async void RunSql_Click(object sender, RoutedEventArgs e)
    {
        var text = SqlEditor.Text.Trim();
        if (text.Length == 0) { SqlMessage.Text = "Type some SQL first, or pick a template."; return; }
        if (!_status.DatabaseReady) { SqlMessage.Text = "The database is offline - start the game first."; return; }
        var unbounded = DbHistory.SplitStatements(text).FirstOrDefault(s =>
            Regex.IsMatch(s, @"^\s*(UPDATE|DELETE)\b", RegexOptions.IgnoreCase) && !Regex.IsMatch(s, @"\bWHERE\b", RegexOptions.IgnoreCase));
        if (unbounded != null && MessageBox.Show("This statement has no WHERE clause and changes every row of the table:\n\n" + unbounded +
                "\n\nRun it anyway? (You can undo it afterwards.)", "Change all rows?", MessageBoxButton.OKCancel, MessageBoxImage.Warning) != MessageBoxResult.OK)
            return;
        SqlMessage.Text = "Running…";
        var firstLine = text.Split('\n')[0].Trim();
        var warnings = new List<string>();
        var r = await Task.Run(() => History.Run(text, firstLine.Length > 80 ? firstLine[..80] + "…" : firstLine, warnings));
        RefreshHistory();
        if (!r.Ok)
        {
            SqlMessage.Text = "Error: " + r.Error;
            return;
        }
        var last = r.Results.LastOrDefault(x => x.Columns.Count > 0);
        SqlGrid.ItemsSource = last != null ? ToDataTable(last).DefaultView : null;
        SqlMessage.Text = last != null
            ? $"{last.Rows.Count} row(s){(last.Truncated ? " (truncated)" : "")}"
            : "Done." + (warnings.Count > 0 ? " Note: " + warnings[0] : "");
        if (_table != null && !DbHistory.IsReadOnly(text)) _ = LoadBrowseAsync();
    }

    private void Template_Selected(object sender, SelectionChangedEventArgs e)
    {
        if (TemplateCombo.SelectedIndex <= 0) return;
        var t = _table != null ? DbHistory.QuoteIdent(_table) : "TableName";
        string col = (ScaleColumnCombo.SelectedItem as ComboBoxItem)?.Tag as string ?? "ColumnName";
        SqlEditor.Text = TemplateCombo.SelectedIndex switch
        {
            1 => $"SELECT * FROM {t} LIMIT 100;",
            2 => $"UPDATE {t} SET {DbHistory.QuoteIdent(col)} = {DbHistory.QuoteIdent(col)} * 2 WHERE 1=1;",
            3 => $"UPDATE {t} SET {DbHistory.QuoteIdent(col)} = 1.0 WHERE rowid = 1;",
            4 => "SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%ColumnName%';",
            _ => "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;",
        };
        TemplateCombo.SelectedIndex = 0;
        SqlEditor.Focus();
    }

    private void SaveSqlAsMod_Click(object sender, RoutedEventArgs e)
    {
        var text = SqlEditor.Text.Trim();
        if (text.Length == 0 || DbHistory.SplitStatements(text).All(DbHistory.IsReadOnly))
        {
            SqlMessage.Text = "Only statements that change data can be saved as a mod.";
            return;
        }
        AddMod(text.Split('\n')[0].Trim(), text);
    }

    // ───────────── history & mods ─────────────

    private void RefreshHistory()
    {
        HistoryList.ItemsSource = null;
        HistoryList.ItemsSource = History.Changes;
        NoHistoryTxt.Visibility = History.Changes.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
    }

    private void RefreshMods()
    {
        ModList.ItemsSource = null;
        ModList.ItemsSource = _main.Settings.DbMods;
        NoModsTxt.Visibility = _main.Settings.DbMods.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
        _main.HomePage.RefreshSummary();
    }

    private void AddMod(string name, string sql)
    {
        _main.Settings.DbMods.Add(new DbMod { Name = name.Length > 60 ? name[..60] : name, Sql = sql, Enabled = true });
        _main.Settings.Save();
        RefreshMods();
        _main.SetStatus($"Saved as mod \"{name}\" - it will be applied every time the game starts.");
    }

    private async void Undo_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as Button)?.Tag is not DbChange change) return;
        var r = await Task.Run(() => History.Undo(change));
        RefreshHistory();
        _main.SetStatus(r.Ok ? $"Undone: {change.Description}" : "Undo failed: " + r.Error);
        if (_table != null) _ = LoadBrowseAsync();
    }

    private void SaveChangeAsMod_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as Button)?.Tag is DbChange change) AddMod(change.Description, change.Sql);
    }

    private void ModEnabled_Click(object sender, RoutedEventArgs e)
    {
        _main.Settings.Save();
        _main.HomePage.RefreshSummary();
    }

    private void ModName_LostFocus(object sender, RoutedEventArgs e) => _main.Settings.Save();

    private async void ApplyMod_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as Button)?.Tag is not DbMod mod) return;
        if (!_status.DatabaseReady) { _main.SetStatus("The database is offline - start the game first."); return; }
        var warnings = new List<string>();
        var r = await Task.Run(() => History.Run(mod.Sql, "Mod: " + mod.Name, warnings));
        RefreshHistory();
        _main.SetStatus(r.Ok ? $"Applied mod \"{mod.Name}\"." : $"Mod \"{mod.Name}\" failed: {r.Error}");
    }

    private void DeleteMod_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as Button)?.Tag is not DbMod mod) return;
        if (MessageBox.Show($"Delete the saved mod \"{mod.Name}\"?\n\nIt will no longer be applied when the game starts. Changes already made in the running game stay until it closes.",
                "Delete mod", MessageBoxButton.OKCancel, MessageBoxImage.Question) != MessageBoxResult.OK) return;
        _main.Settings.DbMods.Remove(mod);
        _main.Settings.Save();
        RefreshMods();
    }

    private void Segment_Checked(object sender, RoutedEventArgs e)
    {
        if (BrowsePanel == null) return;
        BrowsePanel.Visibility = BrowseSeg.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
        SqlPanel.Visibility = SqlSeg.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
        HistoryPanel.Visibility = HistorySeg.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
        if (HistorySeg.IsChecked == true) { RefreshHistory(); RefreshMods(); }
    }

    private void GoHome_Click(object sender, RoutedEventArgs e) => _main.ShowPage("home");
}
