package com.travel.intelligence.api.user.application;

import com.travel.intelligence.api.user.domain.UserAccount;
import java.util.Optional;

public interface UserAccountStore {

    Optional<UserAccount> findById(Long id);

    Optional<UserAccount> findByUsername(String username);

    Optional<UserAccount> findByEmail(String email);

    boolean existsByUsername(String username);

    boolean existsByEmail(String email);

    UserAccount save(UserAccount account);
}
