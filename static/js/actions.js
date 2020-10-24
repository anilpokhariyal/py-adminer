  $(document).ready(function (){
       $('.datatable').DataTable();
       //select/deselect databases
       $(document).on("click","#check_all_db",function (){
           if($(this).is(":checked")) {
               $(".db_check").attr("checked", true);
           }else{
               $(".db_check").attr("checked", false);
           }
           count_selected_databases();
       });

       $(document).on('click','.db_check',function (){
           count_selected_databases();
       });

       $(document).on('click','#drop_databases',function (){
          if(count_selected_databases()>0){
              if(confirm("Are you sure to drop database?")) {
                  $(this).closest('form').submit();
              }
          }else{
            alert("Please select at least one database to drop.");
          }
       });
    });

    function count_selected_databases(){
        let count_databases = $('.db_check:checked').length;
        $('#drop_databases').text("Drop ("+count_databases+")");
        return count_databases;
    }
