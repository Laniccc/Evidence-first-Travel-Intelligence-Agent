package com.travel.intelligence.api.user.web.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record RegisterRequest(
        @NotBlank @Size(min = 3, max = 40) String username,
        @NotBlank @Email @Size(max = 160) String email,
        @NotBlank @Size(min = 6, max = 80) String password,
        @Size(max = 80) String displayName
) {
}
