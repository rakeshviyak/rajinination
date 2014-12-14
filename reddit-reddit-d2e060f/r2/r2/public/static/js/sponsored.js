function update_box(elem) {
   $(elem).prevAll('*[type="checkbox"]:first').prop('checked', true);
};

function update_bid(elem) {
    var form = $(elem).parents(".campaign");
    var is_targeted = $("#targeting").prop("checked");
    var bid = parseFloat(form.find('*[name="bid"]').val());
    var ndays = ((Date.parse(form.find('*[name="enddate"]').val()) -
             Date.parse(form.find('*[name="startdate"]').val())) / (86400*1000));
    ndays = Math.round(ndays);

    // min bid is slightly higher for targeted promos
    var minimum_daily_bid = is_targeted ? $("#bid").data("min_daily_bid") * 1.5 : 
                                          $("#bid").data("min_daily_bid");
    $(".minimum-spend").removeClass("error");
    if (bid < ndays * minimum_daily_bid) {
        $(".bid-info").addClass("error");
        if (is_targeted) {
            $("#targeted_minimum").addClass("error");
        } else {
            $("#no_targeting_minimum").addClass("error");
        }

        form.find('button[name="create"], button[name="edit"]')
            .prop("disabled", "disabled")
            .addClass("disabled");
    } else {
        $(".bid-info").removeClass("error");
        form.find('button[name="create"], button[name="edit"]')
            .removeProp("disabled")
            .removeClass("disabled");
    }

    $(".bid-info").html("&nbsp; &rarr;" + 
                        "<b>$" + (bid/ndays).toFixed(2) +
         "</b> per day for <b>" + ndays + " day(s)</b>");
 }

var dateFromInput = function(selector, offset) {
   if(selector) {
     var input = $(selector);
     if(input.length) {
        var d = new Date();
        offset = $.with_default(offset, 0);
        d.setTime(Date.parse(input.val()) + offset);
        return d;
     }
   }
};

function attach_calendar(where, min_date_src, max_date_src, callback, min_date_offset) {
     $(where).siblings(".datepicker").mousedown(function() {
            $(this).addClass("clicked active");
         }).click(function() {
            $(this).removeClass("clicked")
               .not(".selected").siblings("input").focus().end()
               .removeClass("selected");
         }).end()
         .focus(function() {
          var target = $(this);
          var dp = $(this).siblings(".datepicker");
          if (dp.children().length == 0) {
             dp.each(function() {
               $(this).datepicker(
                  {
                      defaultDate: dateFromInput(target),
                          minDate: dateFromInput(min_date_src, min_date_offset),
                          maxDate: dateFromInput(max_date_src),
                          prevText: "&laquo;", nextText: "&raquo;",
                          altField: "#" + target.attr("id"),
                          onSelect: function() {
                              $(dp).addClass("selected").removeClass("clicked");
                              $(target).blur();
                              if(callback) callback(this);
                          }
                })
              })
              .addClass("drop-choices");
          };
          dp.addClass("inuse active");
     }).blur(function() {
        $(this).siblings(".datepicker").not(".clicked").removeClass("inuse");
     }).click(function() {
        $(this).siblings(".datepicker.inuse").addClass("active");
     });
}

function targeting_on(elem) {
    $(elem).parents(".campaign").find(".targeting")
        .find('*[name="sr"]').prop("disabled", "").end().slideDown();

    update_bid(elem);
}

function targeting_off(elem) {
    $(elem).parents(".campaign").find(".targeting")
        .find('*[name="sr"]').prop("disabled", "disabled").end().slideUp();

    update_bid(elem);
}

(function($) {

function get_flag_class(flags) {
    var css_class = "";
    if(flags.free) {
        css_class += " free";
    }
    if(flags.live) {
        css_class += " live";
    }
    if(flags.complete) {
        css_class += " complete";
    }
    else {
        if(flags.sponsor) {
            css_class += " sponsor";
        }
        if(flags.paid) {
            css_class += " paid";
        }
    }
    return css_class
}

$.new_campaign = function(indx, start_date, end_date, duration, 
                          bid, targeting, flags) {
    cancel_edit(function() {
      var data =('<input type="hidden" name="startdate" value="' + 
                 start_date +'"/>' + 
                 '<input type="hidden" name="enddate" value="' + 
                 end_date + '"/>' + 
                 '<input type="hidden" name="bid" value="' + bid + '"/>' +
                 '<input type="hidden" name="targeting" value="' + 
                 (targeting || '') + '"/>' +
                 '<input type="hidden" name="indx" value="' + indx + '"/>');
      if (flags && flags.pay_url) {
          data += ("<input type='hidden' name='pay_url' value='" + 
                   flags.pay_url + "'/>");
      }
      if (flags && flags.view_live_url) {
          data += ("<input type='hidden' name='view_live_url' value='" + 
                   flags.view_live_url + "'/>");
      }
      var row = [start_date, end_date, duration, "$" + bid, targeting, data];
      $(".existing-campaigns .error").hide();
      var css_class = get_flag_class(flags);
      $(".existing-campaigns table").show()
      .insert_table_rows([{"id": "", "css_class": css_class, 
                           "cells": row}], -1);
      $.set_up_campaigns()
        });
   return $;
};

$.update_campaign = function(indx, start_date, end_date, 
                             duration, bid, targeting, flags) {
    cancel_edit(function() {
            $('.existing-campaigns input[name="indx"]')
                .filter('*[value="' + (indx || '0') + '"]')
                .parents("tr").removeClass()
            .addClass(get_flag_class(flags))
                .children(":first").html(start_date)
                .next().html(end_date)
                .next().html(duration)
                .next().html("$" + bid).removeClass()
                .next().html(targeting)
                .next()
                .find('*[name="startdate"]').val(start_date).end()
                .find('*[name="enddate"]').val(end_date).end()
                .find('*[name="targeting"]').val(targeting).end()
                .find('*[name="bid"]').val(bid).end()
                .find("button, span").remove();
            $.set_up_campaigns();
        });
};

$.set_up_campaigns = function() {
    var edit = "<button>edit</button>";
    var del = "<button>delete</button>";
    var pay = "<button>pay</button>";
    var free = "<button>free</button>";
    var repay = "<button>change</button>";
    var view = "<button>view live</button>";
    $(".existing-campaigns tr").each(function() {
            var tr = $(this);
            var td = $(this).find("td:last");
            var bid_td = $(this).find("td:first").next().next().next()
                .addClass("bid");
            var target_td = $(this).find("td:nth-child(5)")
            if(td.length && ! td.children("button, span").length ) {
                if(tr.hasClass("live")) {
                    $(target_td).append($(view).addClass("view")
                            .click(function() { view_campaign(tr) }));
                }
                /* once paid, we shouldn't muck around with the campaign */
                if(!tr.hasClass("complete")) {
                    if (tr.hasClass("sponsor") && !tr.hasClass("free")) {
                        $(bid_td).append($(free).addClass("free")
                                     .click(function() { free_campaign(tr) }))
                    }
                    else if (!tr.hasClass("paid")) {
                        $(bid_td).prepend($(pay).addClass("pay fancybutton")
                                     .click(function() { pay_campaign(tr) }));
                    } else if (tr.hasClass("free")) {
                        $(bid_td).addClass("free paid")
                            .prepend("<span class='info'>freebie</span>");
                    } else {
                        (bid_td).addClass("paid")
                            .prepend($(repay).addClass("pay fancybutton")
                                     .click(function() { pay_campaign(tr) }));
                    }
                    var e = $(edit).addClass("edit fancybutton")
                        .click(function() { edit_campaign(tr); });
                    var d = $(del).addClass("d fancybutton")
                        .click(function() { del_campaign(tr); });
                    $(td).append(e).append(d);
                }
                else {
                    $(td).append("<span class='info'>complete/live</span>");
                    $(bid_td).addClass("paid")
                }
            }
        });
    return $;

}

}(jQuery));

function detach_campaign_form() {
    /* remove datepicker from fields */
    $("#campaign").find(".datepicker").each(function() {
            $(this).datepicker("destroy").siblings().unbind();
        });

    /* clone and remove original */
    var orig = $("#campaign");
    var campaign = orig.clone(true);
    orig.remove();
    return campaign;
}

function cancel_edit(callback) {
    if($("#campaign").parents('tr:first').length) {
        var tr = $("#campaign").parents("tr:first").prev();
        /* copy the campaign element */
        /* delete the original */
        $("#campaign").fadeOut(function() {
                $(this).parent('tr').prev().fadeIn();
                var td = $(this).parent();
                var campaign = detach_campaign_form();
                td.delete_table_row(function() {
                        tr.fadeIn(function() {
                                $(".existing-campaigns").before(campaign);
                                campaign.hide();
                                if(callback) { callback(); }
                            });
                    });
            });
    } else {
        if ($("#campaign:visible").length) {
            $("#campaign").fadeOut(function() {
                    if(callback) { 
                        callback();
                    }});
        }
        else if (callback) {
            callback();
        }
    }
}

function del_campaign(elem) {
    var indx = $(elem).find('*[name="indx"]').val();
    var link_id = $("#campaign").find('*[name="link_id"]').val();
    $.request("delete_campaign", {"indx": indx, "link_id": link_id},
              null, true, "json", false);
    $(elem).children(":first").delete_table_row();
}


function edit_campaign(elem) {
    /* find the table row in question */
    var tr = $(elem).get(0);

    if ($("#campaign").parents('tr:first').get(0) != tr) {

        cancel_edit(function() {

            /* copy the campaign element */
            var campaign = detach_campaign_form();

            $(".existing-campaigns table")
                .insert_table_rows([{"id": "edit-campaign-tr",
                                "css_class": "", "cells": [""]}], 
                    tr.rowIndex + 1);
            $("#edit-campaign-tr").children('td:first')
                .attr("colspan", 6).append(campaign).end()
                .prev().fadeOut(function() { 
                        var data_tr = $(this);
                        var c = $("#campaign");
                        $.map(['startdate', 'enddate', 'bid', 'indx'], 
                              function(i) {
                                  i = '*[name="' + i + '"]';
                                  c.find(i).val(data_tr.find(i).val());
                              });
                        /* check if targeting is turned on */
                        var targeting = data_tr
                            .find('*[name="targeting"]').val();
                        var radios=c.find('*[name="targeting"]');
                        if (targeting) {
                            radios.filter('*[value="one"]')
                                .prop("checked", "checked");
                            c.find('*[name="sr"]').val(targeting).prop("disabled", "").end()
                                .find(".targeting").show();
                        }
                        else {
                            radios.filter('*[value="none"]')
                                .prop("checked", "checked");
                            c.find('*[name="sr"]').val("").prop("disabled", "disabled").end()
                                .find(".targeting").hide();
                        }
                        /* attach the dates to the date widgets */
                        init_startdate();
                        init_enddate();
                        c.find('button[name="edit"]').show().end()
                            .find('button[name="create"]').hide().end();
                        update_bid('*[name="bid"]');
                        c.fadeIn();
                    } );
            }
            );
    }
}

function create_campaign(elem) {
    cancel_edit(function() {;
            init_startdate();
            init_enddate();
            $("#campaign")
                .find('button[name="edit"]').hide().end()
                .find('button[name="create"]').show().end()
                .find('input[name="indx"]').val('').end()
                .find('input[name="sr"]').val('').end()
                .find('input[name="targeting"][value="none"]')
                                .prop("checked", "checked").end()
                .find(".targeting").hide().end()
                .find('*[name="sr"]').val("").prop("disabled", "disabled").end()
                .fadeIn();
            update_bid('*[name="bid"]');
        });
}

function free_campaign(elem) {
    var indx = $(elem).find('*[name="indx"]').val();
    var link_id = $("#campaign").find('*[name="link_id"]').val();
    $.request("freebie", {"indx": indx, "link_id": link_id},
              null, true, "json", false);
    $(elem).find(".free").fadeOut();
    return false; 
}

function pay_campaign(elem) {
    $.redirect($(elem).find('input[name="pay_url"]').val());
}

function view_campaign(elem) {
    $.redirect($(elem).find('input[name="view_live_url"]').val());
}
