library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity RGB is
    Port ( Din    : in  STD_LOGIC_VECTOR(11 downto 0);
           Nblank : in  STD_LOGIC;
           R      : out STD_LOGIC_VECTOR(7 downto 0);
           G      : out STD_LOGIC_VECTOR(7 downto 0);
           B      : out STD_LOGIC_VECTOR(7 downto 0));
end RGB;

architecture Behavioral of RGB is
begin
    R <= Din(11 downto 8) & Din(11 downto 8) when Nblank = '1' else (others => '0');
    G <= Din(7 downto 4)  & Din(7 downto 4)  when Nblank = '1' else (others => '0');
    B <= Din(3 downto 0)  & Din(3 downto 0)  when Nblank = '1' else (others => '0');
end Behavioral;
