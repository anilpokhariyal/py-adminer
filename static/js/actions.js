$(document).ready(function () {
  $(".datatable").DataTable({
    order: [],
    initComplete: function () {
      $(document).trigger("pyDatatableInit");
    },
  });

  $(document).on("click", "#check_all_db", function () {
    var on = $(this).prop("checked");
    $(".db_check").prop("checked", on);
    count_selected_databases();
  });

  $(document).on("click", ".db_check", function () {
    count_selected_databases();
  });

  function selectedDatabaseNames() {
    return $(".db_check:checked")
      .map(function () {
        return $(this).val();
      })
      .get();
  }

  function trySubmitDropDatabases() {
    var names = selectedDatabaseNames();
    var n = names.length;
    if (n === 0) {
      alert("Select at least one database in the table below, then use “Drop selected databases”.");
      return;
    }
    var list = names.join(", ");
    var msg =
      "You are about to permanently delete " +
      n +
      " database" +
      (n === 1 ? "" : "s") +
      ":\n\n" +
      list +
      "\n\nThis cannot be undone. Continue?";
    if (!window.confirm(msg)) {
      return;
    }
    document.forms.database_actions.submit();
  }

  $(document).on("click", "#drop_databases_menu", function () {
    trySubmitDropDatabases();
  });

  $(document).on("click", ".add_another_search", function () {
    $(".search_row").append($(".pysearch").clone());
    $(".tbs-field-value").last().val("");
  });

  $(document).on("click", ".remove_search", function () {
    $(this).closest(".pysearch").remove();
  });

  count_selected_databases();
});

function count_selected_databases() {
  var names = $(".db_check:checked")
    .map(function () {
      return $(this).val();
    })
    .get();
  var n = names.length;
  var $btn = $("#drop_databases_menu");
  var $hint = $("#drop_db_selection_hint");
  if ($hint.length) {
    if (n === 0) {
      $hint.text("No databases selected.");
    } else if (n === 1) {
      $hint.text('1 selected: "' + names[0] + '"');
    } else {
      $hint.text(n + " selected: " + names.slice(0, 3).join(", ") + (n > 3 ? ", …" : ""));
    }
  }
  if ($btn.length) {
    $btn.prop("disabled", n === 0);
  }
  var $zip = $("#export_databases_zip_btn");
  if ($zip.length) {
    $zip.prop("disabled", n === 0);
  }
  return n;
}
