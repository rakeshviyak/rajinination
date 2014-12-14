jQuery(document).ready(function(){
  $(".alert").alert();
  $("[rel=tooltip]").tooltip({
	container:'body'
  });
  $('#myModal').modal('hide');
  $('#uploadModal').modal('hide');
  $('.dropdown-toggle').dropdown();
  $('#myTab a:first').tab('show');
  $('#side-bar').affix();
  ajaxvote();
  ajaxpopover();
  
  $(window).scroll(function() {
		if($(this).scrollTop() != 0) {
			$('#toTop').fadeIn();	
		} else {
			$('#toTop').fadeOut();
		}
	});
 
	$('#toTop').click(function() {
		$('body,html').animate({scrollTop:0},800);
	});	
  
  
  
  var sideBarNavWidth=$('#right-bar').width() - parseInt($('#side-bar').css('paddingLeft')) - parseInt($('#side-bar').css('paddingRight'));
$('#side-bar').css('width', sideBarNavWidth);	
  
  
	var isLoading = false;
	
	$.fn.doesExist = function(){
    return jQuery(this).length > 0;
	};
	
	$(window).scroll(function () {
                   // Start loading when 100px from the bottom
			
				if ($('#refreshnew').doesExist()==true){   
                   if ($(window).scrollTop() + $(window).height() > $('#refreshnew').height() - 100 && !isLoading && $(LoaddingComment).doesExist()==true) {
                       refreshcontainer('new');
                   }
				   }
				if ($('#refreshhot').doesExist()==true){
				   if ($(window).scrollTop() + $(window).height() > $('#refreshhot').height() - 100 && !isLoading && $(LoaddingComment).doesExist()==true) {
						refreshcontainer('hot');
                   }
				   }
				if ($('#refreshtag').doesExist()==true){   
                   if ($(window).scrollTop() + $(window).height() > $('#refreshtag').height() - 100 && !isLoading && $(LoaddingComment).doesExist()==true) {
						var tagname=$('#refreshtag').attr("value");
						refreshcontainer('tag&tagname='+tagname);
                   }
				   }
               });			
				
		function refreshcontainer(a){
			$('#LoaddingComment').removeClass('hide');
			page=$('#endofpage').attr('value');
			isLoading = true;
			$.ajax({
				type: "POST",
				dataType:"json",
				url: '/loadpage?type='+a+'&p='+page, 
				success: refreshhtml,  
				});
			return false;
			}
		
		function refreshhtml(e){
				
				$('#'+e.container).append(e.html);
				$('#endofpage').attr('value',e.page);
				if (e.nextpage==1){
					isLoading = false;
				}
				if (e.nextpage==0){
					
					$('#endofpage').removeClass('hide');
				}
				$('#LoaddingComment').addClass('hide');
				
				//Ajax load content
				FB.XFBML.parse(document.getElementById(e.page));
				twttr.widgets.load(document.getElementById(e.page));
				ajaxvote();
				ajaxpopover();
				
			} 
	
   $('.image-preview').click(function() {
		var topAlign = $('#topAlign').attr('value');
		var bottomAlign = $('#bottomAlign').attr('value');
		var font = $('#ddlFont').val();
		var fontsize = $('#txtSize').val();
		var color = $('#ddlColor').val();
		var topCaption = $('#txtTop').val();
		var bottomCaption = $('#txtBottom').val();
		var imagelink = $('#orginalimage').attr("value");
		$.ajax({
			type: "POST",
			dataType:"json",
			url: '/generate', 
			data : {'topAlign': topAlign, 'bottomAlign': bottomAlign, 'font': font, 'fontsize': fontsize, 'color': color, 'topCaption': topCaption, 'bottomCaption': bottomCaption, 'imagelink': imagelink}, 
			success: updateimage,  
        });
    return false;
	});
	
	function updateimage(e) {
		$('#selectimagelink').attr('src','/img?img_id='+e.imagekey);
		$('#previewimage').attr('value',e.imagekey);	
		}
	
	$('div.tag-select').on('click', 'button[data-name]', function() {
        var select = $(this).data('name').split(',');
        var elem = $('#realform > input[name="'+select[0]+'"]');
        if(elem.length !== 0)
            elem.remove();
        if(elem.attr('value') !== select[1])
            $('<input type="hidden" name="'+select[0]+'" value="'+select[1]+'" />').appendTo('#realform');
    });
	
  $('.select-controls').each(function(){
        
        var name    = $(this).attr('data-toggle-name');
        var hidden  = $('input[name="' + name + '"]');
        var type    = $(this).attr('data-toggle');
        var check   = [];

        $('button', $(this)).each(function(){
            $(this).on('click', function(){
                if($(this).val() == hidden.val())
                {
                    switch (type) {
                        case 'button': $(this).removeClass('active'); hidden.val(0); break;
                        case 'buttons-checkbox': $(this).removeClass('active'); break;
                        default: hidden.val($(this).val());
                    }
                }
                else
                {
                    switch (type) {
                        case 'button': $(this).addClass('active'); hidden.val(1); break;
                        case 'buttons-checkbox': $(this).addClass('active'); break;
                        default: hidden.val($(this).val());
                    }
                }
            });

            if($(this).val() == hidden.val()) $(this).addClass('active');
        });
    });
  
  
 
  $('.previewimage').click(function() {
		var getvalue = $(this).attr('name');
		$('#previewimagelink').attr('src',getvalue);	
		
		});
  
  $('.selectimage').click(function() {
		var getvalue = $(this).attr('name');
		$('#selectimagelink').attr('src',getvalue);	
		$('#orginalimage').attr('value',getvalue);	
		});

  
	
  $('.sidepagenext').click(function() {
		var getvalue = $(this).attr('title');
		var getid = $(this).attr('id');
		
		if (getvalue && getid){
		$.ajax({
			type: "POST",
			dataType:"json",
			url: '/siderefresh', 
			data : {'p': getid, 'action': getvalue}, 
			success: alert("hjads"),  
			});
		return false;
		}
		
		});
	
  function ajaxvote(){ 
	$('.vote').on("click",function() {
		var getvalue = $(this).attr('name');
		var getid = $(this).attr('id');
		if (getvalue && getid){
		$.ajax({
			type: "POST",
			dataType:"json",
			url: '/vote', 
			data : {'imgid': getid, 'action': getvalue}, 
			success: updatevote,  
			});
		return false;
			}
		})
	};
	
	function contains(a,b){
		if (a.indexOf(b) > -1) {
			return true;
			} 
		else {
			return false;
			}
		}
	function updatevote(e) {
           if (e.status == "ok") {
                $('#'+e.id+'.votes').text(e.votes);
				if(e.action=="1"){
					var voteup=($('#'+e.id+'.up').attr('class'));
					
					var votedown=($('#'+e.id+'.down').attr('class'));
					var voteupflag=contains(voteup,'active');
					if (voteupflag!=true){
						$('#'+e.id+'.up').attr('class',voteup+' active');
						}
					$('#'+e.id+'.down').attr('class',votedown.replace('active',''));
					}
                if(e.action=="-1"){
					var voteup=($('#'+e.id+'.up').attr('class'));
					var votedown=($('#'+e.id+'.down').attr('class'));
					var votedownflag=contains(votedown,'active');
					if (votedownflag!=true){
						$('#'+e.id+'.down').attr('class',votedown+' active');
						}
					$('#'+e.id+'.up').attr('class',voteup.replace('active',''));
					}
                }
            else if(e.status=="err"){
				popoveron(e.action,e.id);
				}
        }
		 
		function popoveron(action,id){
			if (action=="ThumpsUp"){
				$('#'+id+'.down').popover('hide');
				$('#'+id+'.up').popover('show');
				}
			else if (action=="ThumpsDown"){
				$('#'+id+'.up').popover('hide');
				$('#'+id+'.down').popover('show');
				}
		}
		 
		function ajaxpopover(){ 
		 $('.vote').popover({
				placement: 'bottom',
				container:'body',
				html: 'true',
				title : '<span class="text-info"><strong><u><a href="#myModal" data-toggle="modal">Login</a></u> to Vote</strong></span>'+
						'<a type="button" id="close" class="close" onclick="$(&quot;.vote&quot;).popover(&quot;hide&quot;);">&times;</a>',
				content : '<h6>You need to be <a href="#myModal" role="button" class="btn" data-toggle="modal"> Logged in </a> to do this</h6>',
				trigger:'manual'
				});
		}
});

	