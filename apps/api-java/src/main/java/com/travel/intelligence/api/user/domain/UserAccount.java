package com.travel.intelligence.api.user.domain;

import java.time.Instant;

public class UserAccount {

    private Long id;
    private String username;
    private String email;
    private String passwordHash;
    private String displayName;
    private UserRole role = UserRole.USER;
    private Instant createdAt = Instant.now();

    public UserAccount(String username, String email, String passwordHash, String displayName, UserRole role) {
        this(null, username, email, passwordHash, displayName, role, Instant.now());
    }

    public UserAccount(
            Long id,
            String username,
            String email,
            String passwordHash,
            String displayName,
            UserRole role,
            Instant createdAt) {
        this.id = id;
        this.username = username;
        this.email = email;
        this.passwordHash = passwordHash;
        this.displayName = displayName;
        this.role = role != null ? role : UserRole.USER;
        this.createdAt = createdAt != null ? createdAt : Instant.now();
    }

    public Long getId() {
        return id;
    }

    public String getUsername() {
        return username;
    }

    public String getEmail() {
        return email;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public String getDisplayName() {
        return displayName;
    }

    public UserRole getRole() {
        return role;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void updateProfile(String displayName, String email) {
        if (displayName != null && !displayName.isBlank()) {
            this.displayName = displayName.trim();
        }
        if (email != null && !email.isBlank()) {
            this.email = email.trim().toLowerCase();
        }
    }
}
