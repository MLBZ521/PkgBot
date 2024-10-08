// Internal PkgBot JavaScript

// ################################################################################################
// Functions

function verify_file(event, file, form) {
	// Verify a file was selected before uploading

	event.preventDefault();
	console.log("Verifying a file was selected...");

	if (file) {
		// A file was selected
		console.log("Uploading file...");
		form.submit()
	}
	else {
		// A file was not selected
		console.warn("[WARNING] A file was not selected");
		event.target.setCustomValidity("Please select a file to upload!");
		event.target.reportValidity();
	}

}


function config_table(tables) {

	$("#" + this.id).DataTable(
		{
			"order": [
				[ $('.primary-column').index(), "desc" ]
			],
			"search": {
				"regex": true
			},
			"columnDefs": [
				{
					"targets": $('.sorting-disabled').index(),
					"orderable": false
				} 
			]
		}
	);

}


function count_characters() {

	this.addEventListener("input", count_characters)

	const max_length = $(this).attr("maxlength");
	const current_length = $(this).val().length;
	let characters_remaining = max_length - current_length;
	let counter = $(this).next(".form-text");

	counter.text(current_length + "/" + max_length);

	if (characters_remaining === 0) {
		// Change text color to "danger" when there are 0 characters remaining
		counter.removeClass("text-muted");
		counter.removeClass("text-warning");
		counter.addClass("text-danger");
	}
	else if (characters_remaining <= 500) {
		// Change text color to "warning" when there are less than 500 characters remaining
		counter.removeClass("text-danger");
		counter.removeClass("text-muted");
		counter.addClass("text-warning");
	}
	else {
		counter.removeClass("text-danger");
		counter.removeClass("text-warning");
		counter.addClass("text-muted");
	}

}


// ################################################################################################
// Document Event Listeners

// Menu/navigation item to upload recipe configuration files
if ( document.getElementById('button_upload_recipes') ) {

	document.getElementById('button_upload_recipes').addEventListener('click', (e) => {
		const file_input = document.getElementById('recipes_file').value;
		const form = document.getElementById("form_upload_recipes")
		verify_file(e, file_input, form);
	});

}

// ################################################################################################
// On load

$(document).ready(function() {

	$(".pkgbot-table").each(config_table);
	$(".count-text").each(count_characters);

})
